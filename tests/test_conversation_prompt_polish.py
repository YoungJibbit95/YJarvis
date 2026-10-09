"""YJCOM-01 prompt/identity/latency contracts without Ollama or OS actions."""
import asyncio
import json
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from jarvis_agent.db import Database
from jarvis_agent.orchestration.legacy_responses import LegacyResponses
from jarvis_agent.profile import DEFAULT_PROFILE, build_persona_system_prompt, load_profile
from jarvis_agent.orchestration import legacy_responses as response_module


def _responses(db):
    return LegacyResponses(
        db, SimpleNamespace(publish=None), history_limit=6,
        memory_limit=2, enable_llm_tool_summary=False,
        token_flush_interval_seconds=0.02, token_flush_min_chars=8,
    )


def test_default_identity_is_platform_neutral():
    prompt = build_persona_system_prompt(DEFAULT_PROFILE)
    assert "Mac" not in prompt and "macOS" not in prompt
    assert "Windows" not in prompt  # no unsupported platform/capability claims
    assert "lokaler" in prompt.lower()
    assert "Deutsch" in prompt or "deutsch" in prompt
    assert "Rueckfrage" in prompt or "Rückfrage" in prompt


def test_legacy_default_identity_is_adjusted_only_in_memory_without_rewriting(tmp_path: Path):
    config_path = tmp_path / "jarvis_profile.json"
    legacy_profile = deepcopy(DEFAULT_PROFILE)
    legacy_profile["persona"]["identity_instructions"] = [
        "Du bist J.A.R.V.I.S., ein hochpraeziser technischer Assistent fuer einen einzelnen Benutzer auf diesem Mac.",
        "Du bist loyal, diskret und sicherheitsorientiert.",
        "Du bist sachlich, schnell und elegant in der Formulierung.",
    ]
    config_path.write_text(json.dumps(legacy_profile, ensure_ascii=False), encoding="utf-8")
    before = config_path.read_bytes()
    first = load_profile(config_path)
    second = load_profile(config_path)
    assert build_persona_system_prompt(first) == build_persona_system_prompt(second)
    assert "diesem Mac" not in build_persona_system_prompt(first)
    assert first["persona"]["style_instructions"] == legacy_profile["persona"]["style_instructions"]
    assert first["safety"] == legacy_profile["safety"]
    assert config_path.read_bytes() == before


def test_custom_profile_and_safety_stay_intact(tmp_path: Path):
    path = tmp_path / "jarvis_profile.json"
    custom = {
        "persona": {
            "identity_instructions": ["Ich bin bewusst Dein Assistent für diesen Mac."],
            "style_instructions": ["Sprich mich mit Commander an."],
            "response_contract": ["Antworte in zwei Sätzen."],
        },
        "safety": {"confirmation_required_patterns": ["custom-protected-action"]},
    }
    path.write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
    saved = path.read_bytes()
    loaded = load_profile(path)
    prompt = build_persona_system_prompt(loaded)
    assert "Commander" in prompt
    assert "diesen Mac" in prompt  # explicitly personal, never auto-migrated
    assert loaded["safety"]["confirmation_required_patterns"] == ["custom-protected-action"]
    assert path.read_bytes() == saved


def test_followup_uses_only_same_session_history_and_memory(tmp_path: Path):
    db = Database(tmp_path / "conversations.db", tmp_path, tmp_path / "whisper.bin")

    async def scenario():
        await db.init()
        for sid in ("main-session", "private-other-session"):
            await db.create_session(sid)
        await db.add_message("main-session", "user", "Was machen wir heute am Projekt?")
        await db.add_message("main-session", "assistant", "Offene Fehler beheben oder Features bauen?")
        await db.add_message("main-session", "user", "Lieber die Probleme.")
        await db.add_memory_item("main-session", "Lieber die Probleme: Das Projekt muss stabiler werden", 0.9)
        await db.add_message("private-other-session", "assistant", "SECRET_OTHER_SESSION")
        await db.add_memory_item("private-other-session", "Lieber die Probleme: SECRETMEMORY einer anderen Session", 1.0)

        response = _responses(db)
        messages = await response._build_prompt_messages("main-session", "Lieber die Probleme.", DEFAULT_PROFILE)
        assert messages[-3:] == [
            {"role": "user", "content": "Was machen wir heute am Projekt?"},
            {"role": "assistant", "content": "Offene Fehler beheben oder Features bauen?"},
            {"role": "user", "content": "Lieber die Probleme."},
        ]
        assert messages.count({"role": "user", "content": "Lieber die Probleme."}) == 1
        full = "\n".join(item["content"] for item in messages)
        assert "Das Projekt muss stabiler werden" in full
        assert "SECRET_OTHER_SESSION" not in full
        assert "SECRETMEMORY" not in full
        assert "Anschlussfragen" in messages[0]["content"] or "vorherigen" in messages[0]["content"]
        # Same-session rephrasings refer to prior answer, not arbitrary OS action.
        await db.add_message("main-session", "user", "Erklär das einfacher.")
        simpler = await response._build_prompt_messages("main-session", "Erklär das einfacher.", DEFAULT_PROFILE)
        assert simpler[-2]["content"] == "Lieber die Probleme."
        assert simpler[-1] == {"role": "user", "content": "Erklär das einfacher."}

    asyncio.run(scenario())


def test_prompt_history_keeps_real_repeated_turns_but_never_appends_duplicate_current(tmp_path: Path):
    db = Database(tmp_path / "history.db", tmp_path, tmp_path / "whisper.bin")

    async def scenario():
        await db.init()
        await db.create_session("s")
        await db.add_message("s", "user", "Warum?")
        await db.add_message("s", "assistant", "Aus diesem Grund.")
        await db.add_message("s", "user", "Warum?")
        prompt = await _responses(db)._build_prompt_messages("s", "Warum?", DEFAULT_PROFILE)
        assert [m["content"] for m in prompt if m["role"] == "user"] == ["Warum?", "Warum?"]
        assert prompt[-1] == {"role": "user", "content": "Warum?"}
    asyncio.run(scenario())


def test_prompt_reads_can_overlap_without_extra_model_calls(monkeypatch):
    started = set()
    all_started = asyncio.Event()

    async def blocking_read(name, value):
        started.add(name)
        if len(started) == 3:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=1.0)
        return value

    db = SimpleNamespace(
        list_recent_messages=lambda session_id, limit: blocking_read(
            "history", [{"role": "user", "content": "Warum?"}]),
        get_tool_learning_stats=lambda: blocking_read("tool-stats", []),
    )
    async def fake_memory(_db, text, *, limit, session_id):
        assert text == "Warum?" and session_id == "s"
        return await blocking_read("memory", [])

    monkeypatch.setattr(response_module, "load_context_snippets", fake_memory)

    async def scenario():
        start = time.perf_counter()
        messages = await asyncio.wait_for(
            _responses(db)._build_prompt_messages("s", "Warum?", DEFAULT_PROFILE),
            timeout=2,
        )
        assert messages[-1] == {"role": "user", "content": "Warum?"}
        assert started == {"history", "memory", "tool-stats"}
        return (time.perf_counter() - start) * 1000

    elapsed_ms = asyncio.run(scenario())
    assert elapsed_ms >= 0  # benchmark fixture time; no real Ollama latency claim
