"""Characterize the public legacy lifecycle using real temporary SQLite databases.

Only model I/O and tool execution are faked; routing, safety, learning, persistence
and compaction run normally. These assertions also run before the extraction.
"""

import asyncio
import sqlite3
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from jarvis_agent.agent_service import AgentService
from jarvis_agent.db import Database
from jarvis_agent.llm import LlmError
from jarvis_agent.orchestration import legacy_responses as response_module
from jarvis_agent.orchestration import legacy_planner as planner_module
from jarvis_agent.orchestration import turn_engine as engine_module
from jarvis_agent.tools import ToolRegistry
from jarvis_agent.tools.base import ToolResult


@pytest.fixture
def rig(tmp_path, monkeypatch):
    for key, value in {
        "JARVIS_ENABLE_TOOL_PLANNER": "0",
        "JARVIS_TOOL_SUMMARY_VIA_LLM": "0",
        "JARVIS_HISTORY_LIMIT": "6",
        "JARVIS_MEMORY_LIMIT": "1",
        "JARVIS_TOKEN_FLUSH_INTERVAL_MS": "20",
        "JARVIS_TOKEN_FLUSH_MIN_CHARS": "8",
    }.items():
        monkeypatch.setenv(key, value)
    db = Database(tmp_path / "test.db", tmp_path, tmp_path / "model.bin")

    async def initialize():
        await db.init()
        await db.create_session("session")

    asyncio.run(initialize())
    trace = []
    events = []

    async def publish(session_id, payload):
        assert session_id == "session"
        assert datetime.fromisoformat(payload["timestamp"]).tzinfo is not None
        expected = {"event", "run_id", "timestamp"}
        expected |= {
            "run_state": {"state", "detail"},
            "token": {"token"},
            "message": {"role", "content"},
        }[payload["event"]]
        if payload.get("state") == "approval_required":
            expected.add("data")
        assert set(payload) == expected
        events.append(payload)
        trace.append("event:" + payload.get("state", payload["event"]))

    for name in ("add_message", "create_approval", "resolve_approval", "add_tool_run",
                 "record_tool_learning", "record_learned_command_result"):
        original = getattr(db, name)

        async def record(*args, _name=name, _original=original, **kwargs):
            result = await _original(*args, **kwargs)
            suffix = ":" + kwargs["role"] if _name == "add_message" else ""
            trace.append("db:" + _name + suffix)
            return result

        monkeypatch.setattr(db, name, AsyncMock(side_effect=record))

    tools = ToolRegistry()

    async def execute(**kwargs):
        # The approval must already be durably approved when execution starts.
        with sqlite3.connect(db.db_path) as connection:
            assert connection.execute("SELECT status FROM approvals").fetchall() == [("approved",)]
        trace.append("tool:execute")
        return ToolResult(success=True, output="Erledigt")

    tools.execute = AsyncMock(side_effect=execute)
    stream = Mock(side_effect=AssertionError("Unexpected LLM stream"))
    planner = AsyncMock(side_effect=AssertionError("Unexpected planner call"))
    summary = AsyncMock(side_effect=AssertionError("Unexpected summary call"))
    monkeypatch.setattr(response_module, "stream_chat", stream)
    monkeypatch.setattr(response_module, "complete_chat", summary)
    monkeypatch.setattr(planner_module, "plan_tool_call", planner)
    monkeypatch.setattr(response_module, "time", SimpleNamespace(perf_counter=lambda: 1.0))
    compact_original = response_module.maybe_compact_session

    async def compact(db, session_id):
        trace.append("memory:compact")
        await compact_original(db, session_id)

    compact_mock = AsyncMock(side_effect=compact)
    monkeypatch.setattr(response_module, "maybe_compact_session", compact_mock)
    monkeypatch.setattr(engine_module, "maybe_compact_session", compact_mock)
    monkeypatch.setattr(engine_module, "time", SimpleNamespace(perf_counter=lambda: 1.0))
    def make_service():
        return AgentService(db, SimpleNamespace(publish=publish), tools, tmp_path / "profile.json")

    service = make_service()

    def enable(setting):
        monkeypatch.setenv(setting, "1")
        return make_service()

    def set_stream(tokens, error=None):
        async def generate(**kwargs):
            for token in tokens:
                yield token
            if error is not None:
                raise error

        stream.side_effect = generate

    return SimpleNamespace(
        db=db, service=service, tools=tools, events=events, trace=trace,
        stream=stream, planner=planner, summary=summary, compact=compact_mock,
        set_stream=set_stream, enable=enable,
    )


def event_order(rig):
    return [event.get("state", event["event"]) for event in rig.events]


async def request_approval(rig, message="oeffne Safari"):
    await rig.service.start_run("session", "run", message)
    approvals = await rig.db.list_pending_approvals()
    assert len(approvals) == 1
    assert approvals[0]["tool_name"] == "open_app"
    assert approvals[0]["tool_input"] == {"app_name": "Safari"}
    rig.tools.execute.assert_not_awaited()
    assert event_order(rig) == ["received", "thinking", "approval_required"]
    assert rig.events[-1]["data"]["approval"] == approvals[0]
    return approvals[0]["id"]


@pytest.mark.parametrize("message, detail, text", [
    ("mach mir eine erinnerung", "Rueckfrage fuer praezisen Auftrag", "Erinnerung"),
    ("Bitte loesch das gesamte System jetzt", "Sicherheitsregel hat Anfrage blockiert", "Sicherheitsgruenden"),
    ("Bitte fuehre das mit sudo aus", "Sicherheitsbestaetigung erforderlich", "Bestaetige"),
    ("/learn-list", "Lernmodus aktualisiert", "Noch keine Befehle"),
    ("mach xyz", "Tool-Aufruf unklar, keine Ausfuehrung", "nicht eindeutig erkannt"),
])
def test_local_outcomes_persist_before_events_without_model_or_execution(rig, message, detail, text):
    async def check():
        await rig.service.start_run("session", "run", message)
        assert event_order(rig) == ["received", "thinking", "message", "done"]
        assert rig.events[-1]["detail"] == detail
        assert text.lower() in rig.events[-2]["content"].lower()
        assert all(event["run_id"] == "run" for event in rig.events)
        rows = await rig.db.list_messages("session")
        assert [(row["role"], row["content"]) for row in rows] == [
            ("user", message), ("assistant", rig.events[-2]["content"]),
        ]
        assert rig.trace == ["db:add_message:user", "event:received", "event:thinking",
                             "db:add_message:assistant", "event:message", "event:done"]
        assert await rig.db.list_pending_approvals() == []
        rig.tools.execute.assert_not_awaited()
        rig.planner.assert_not_awaited()
        rig.stream.assert_not_called()
        rig.compact.assert_not_awaited()

    asyncio.run(check())


def test_confirmation_restores_original_input_but_still_requires_tool_approval(rig):
    original = '/tool open_app {"app_name": "Safari", "note": "sudo example"}'

    async def check():
        await rig.service.start_run("session", "first", original)
        assert event_order(rig) == ["received", "thinking", "message", "done"]
        rig.events.clear()
        await rig.service.start_run("session", "second", "Bestaetige")
        assert event_order(rig) == ["received", "thinking", "thinking", "approval_required"]
        assert rig.events[2]["detail"] == "Sicherheitsbestaetigung akzeptiert"
        pending = await rig.db.list_pending_approvals()
        assert len(pending) == 1
        assert pending[0]["run_id"] == "second"
        assert pending[0]["tool_input"]["note"] == "sudo example"
        assert "session" not in rig.service.pending_confirmations
        assert (await rig.db.list_messages("session"))[-1]["content"] == "Bestaetige"
        rig.tools.execute.assert_not_awaited()

    asyncio.run(check())


def test_new_message_discards_stale_confirmation(rig):
    async def check():
        await rig.service.start_run("session", "first", "sudo example")
        await rig.service.start_run("session", "second", "hallo jarvis")
        assert "session" not in rig.service.pending_confirmations
        rig.set_stream(["Keine offene Bestaetigung."])
        rig.events.clear()
        await rig.service.start_run("session", "third", "Bestaetige")
        assert "approval_required" not in event_order(rig)
        assert not any(event.get("detail") == "Sicherheitsbestaetigung akzeptiert" for event in rig.events)
        assert await rig.db.list_pending_approvals() == []
        rig.tools.execute.assert_not_awaited()

    asyncio.run(check())


@pytest.mark.parametrize("success", [True, False])
def test_learning_trigger_approval_execution_persistence_and_metrics(rig, success):
    async def check():
        await rig.service.start_run("session", "learn", '/learn "fokus" => oeffne Safari')
        learned = await rig.db.get_learned_command("fokus")
        assert learned["tool_name"] == "open_app"
        rig.events.clear()
        approval_id = await request_approval(rig, "fokus")
        original_execute = rig.tools.execute.side_effect

        async def execute(**kwargs):
            await original_execute(**kwargs)
            return ToolResult(success=success, output="Erledigt" if success else "", error=None if success else "offline")

        rig.tools.execute.side_effect = execute
        rig.trace.clear()
        rig.events.clear()
        assert await rig.service.handle_approval_decision(approval_id, "approve") == "approved"
        rig.tools.execute.assert_awaited_once()
        assert (await rig.db.get_approval(approval_id))["status"] == "approved"
        assert event_order(rig) == ["executing", "message", "done" if success else "error"]
        assert ("Erledigt" if success else "offline") in rig.events[1]["content"]
        assert rig.trace == [
            "db:resolve_approval", "event:executing", "tool:execute", "db:add_tool_run",
            "db:record_tool_learning", "db:record_learned_command_result",
            "db:add_message:assistant", "event:message", "event:done" if success else "event:error",
            "memory:compact",
        ]
        stats = (await rig.db.get_tool_learning_stats())[0]
        learned = await rig.db.get_learned_command("fokus")
        for row in (stats, learned):
            assert row["success_count"] == int(success)
            assert row["failure_count"] == int(not success)
        assert learned["usage_count"] == 1
        with sqlite3.connect(rig.db.db_path) as connection:
            assert connection.execute("SELECT run_id, success, result, error FROM tool_runs").fetchall() == [
                ("run", int(success), "Erledigt" if success else "", None if success else "offline"),
            ]
        with pytest.raises(ValueError, match="bereits entschieden"):
            await rig.service.handle_approval_decision(approval_id, "approve")
        rig.tools.execute.assert_awaited_once()
        rig.summary.assert_not_awaited()

    asyncio.run(check())


def test_deny_never_executes_or_records_tool_learning(rig):
    async def check():
        approval_id = await request_approval(rig)
        rig.events.clear()
        assert await rig.service.handle_approval_decision(approval_id, "deny") == "denied"
        assert (await rig.db.get_approval(approval_id))["status"] == "denied"
        assert event_order(rig) == ["message", "done"]
        assert "nichts ausgefuehrt" in rig.events[0]["content"]
        rig.tools.execute.assert_not_awaited()
        rig.db.add_tool_run.assert_not_awaited()
        rig.db.record_tool_learning.assert_not_awaited()
        rig.compact.assert_not_awaited()
        with pytest.raises(ValueError, match="bereits entschieden"):
            await rig.service.handle_approval_decision(approval_id, "approve")

    asyncio.run(check())


@pytest.mark.parametrize("missing", [True, False])
def test_invalid_approval_does_not_execute(rig, missing):
    async def check():
        approval_id = "missing" if missing else await request_approval(rig)
        with pytest.raises(ValueError, match="nicht gefunden" if missing else "Ungueltige Entscheidung"):
            await rig.service.handle_approval_decision(approval_id, "invalid")
        rig.tools.execute.assert_not_awaited()
        rig.db.resolve_approval.assert_not_awaited()

    asyncio.run(check())


def test_stream_batches_tokens_normalizes_final_text_and_preserves_prompt(rig):
    rig.set_stream(["Hallo ", "mein Herr", "."])

    async def check():
        await rig.service.start_run("session", "run", "Erzaehle etwas ueber Sterne")
        assert event_order(rig) == ["received", "thinking", "token", "token", "token", "message", "done"]
        assert [event["token"] for event in rig.events if event["event"] == "token"] == ["Hallo ", "mein Herr", "."]
        assert rig.events[-2]["content"] == "Hallo Sir."
        assert rig.trace[-4:] == ["db:add_message:assistant", "event:message", "event:done", "memory:compact"]
        prompt = rig.stream.call_args.kwargs
        assert prompt["model"] == "qwen2.5:3b-instruct"
        assert prompt["base_url"] == "http://127.0.0.1:11434"
        assert prompt["messages"][0]["role"] == "system"
        assert prompt["messages"][-1] == {"role": "user", "content": "Erzaehle etwas ueber Sterne"}
        assert (await rig.db.list_messages("session"))[-1]["content"] == "Hallo Sir."
        rig.tools.execute.assert_not_awaited()

    asyncio.run(check())


@pytest.mark.parametrize("error, prefix, detail", [
    (LlmError("offline"), "LLM Fehler: offline", "LLM Anfrage fehlgeschlagen"),
    (RuntimeError("unexpected"), "Unerwarteter Fehler: unexpected", "Unbekannter Verarbeitungsfehler"),
])
def test_stream_error_keeps_emitted_tokens_but_does_not_flush_partial_buffer(rig, error, prefix, detail):
    rig.set_stream(["12345678", "short"], error)

    async def check():
        await rig.service.start_run("session", "run", "Erzaehle etwas ueber Sterne")
        assert event_order(rig) == ["received", "thinking", "token", "message", "error"]
        assert rig.events[2]["token"] == "12345678"
        assert rig.events[3]["content"] == prefix
        assert rig.events[4]["detail"] == detail
        assert (await rig.db.list_messages("session"))[-1]["content"] == prefix
        rig.compact.assert_not_awaited()

    asyncio.run(check())


def test_empty_stream_is_visible_model_error_not_successful_canned_reply(rig):
    rig.set_stream([])
    asyncio.run(rig.service.start_run("session", "run", "Erzaehle etwas ueber Sterne"))
    assert event_order(rig) == ["received", "thinking", "message", "error"]
    assert "keine verwertbare Modellantwort" in rig.events[-2]["content"]


def test_stream_compacts_after_eighth_persisted_message(rig):
    rig.set_stream(["Antwort"])

    async def check():
        for index in range(6):
            await rig.db.add_message(session_id="session", role="user", content=f"Sterne Kontext {index}")
        await rig.service.start_run("session", "run", "Erzaehle etwas ueber Sterne")
        assert await rig.db.count_messages("session") == 8
        memories = await rig.db.search_memory("Sterne")
        assert len(memories) == 1
        assert "ASSISTANT: Antwort" in memories[0]["content"]
        assert "Kontext-Erinnerungen:" not in rig.stream.call_args.kwargs["messages"][0]["content"]

    asyncio.run(check())


@pytest.mark.parametrize("planned,valid", [
    ({"decision": "tool", "tool_name": "open_app",
      "tool_input": {"app_name": "Safari"}}, True),
    (None, False),
    ({}, False),
    ({"decision": "tool", "tool_name": "unknown", "tool_input": {}}, False),
    ({"decision": "tool", "tool_name": "open_app", "tool_input": "invalid"}, False),
    ({"decision": "tool", "tool_name": "open_app",
      "tool_input": {"app_name": "Chrome"}}, False),
    (RuntimeError("offline"), False),
])
def test_optional_planner_preserves_validation_and_requires_approval(rig, planned, valid, monkeypatch):
    from jarvis_agent.orchestration import semantic_pilot

    monkeypatch.setattr(semantic_pilot, "supported_legacy_platform", lambda: True)
    rig.service = rig.enable("JARVIS_ENABLE_TOOL_PLANNER")
    rig.planner.side_effect = planned if isinstance(planned, Exception) else None
    rig.planner.return_value = planned
    rig.set_stream(["Keine Aktion."])

    async def check():
        await rig.service.start_run("session", "run", "Aktiviere bitte die App Safari")
        rig.planner.assert_awaited_once()
        assert len(await rig.db.list_pending_approvals()) == int(valid)
        assert rig.events[-1]["state"] == ("approval_required" if valid else "done")
        rig.tools.execute.assert_not_awaited()
        if valid:
            rig.stream.assert_not_called()
        else:
            rig.stream.assert_called_once()

    asyncio.run(check())


def test_heuristic_route_precedes_enabled_planner(rig):
    rig.service = rig.enable("JARVIS_ENABLE_TOOL_PLANNER")
    asyncio.run(request_approval(rig))
    rig.planner.assert_not_awaited()


@pytest.mark.parametrize("summary", ["Erledigt, mein Herr.", "", RuntimeError("offline")])
def test_optional_tool_summary_and_fallback(rig, summary):
    rig.service = rig.enable("JARVIS_TOOL_SUMMARY_VIA_LLM")
    rig.summary.side_effect = summary if isinstance(summary, Exception) else None
    rig.summary.return_value = summary

    async def check():
        approval_id = await request_approval(rig)
        await rig.service.handle_approval_decision(approval_id, "approve")
        rig.summary.assert_awaited_once()
        assert rig.summary.call_args.kwargs["temperature"] == 0.1
        expected = "Erledigt, Sir." if summary == "Erledigt, mein Herr." else "Tool `open_app` ausgefuehrt. Ergebnis: Erledigt"
        assert rig.events[-2]["content"] == expected

    asyncio.run(check())


def test_background_entry_point_schedules_existing_public_coroutine(rig, monkeypatch):
    rig.service.start_run = AsyncMock()

    async def check():
        tasks = []
        create_task = asyncio.create_task
        monkeypatch.setattr(asyncio, "create_task", lambda coro: tasks.append(create_task(coro)))
        assert rig.service.start_run_background("session", "run", "hallo") is None
        await tasks[0]
        rig.service.start_run.assert_awaited_once_with(session_id="session", run_id="run", user_message="hallo")

    asyncio.run(check())


def test_token_interval_flushes_before_size_threshold(rig, monkeypatch):
    ticks = iter([1.0, 1.03, 1.03, 1.04, 1.04])
    monkeypatch.setattr(response_module, "time", SimpleNamespace(perf_counter=lambda: next(ticks)))
    rig.set_stream(["ab", "cd"])
    asyncio.run(rig.service.start_run("session", "run", "Erzaehle etwas ueber Sterne"))
    assert [event["token"] for event in rig.events if event["event"] == "token"] == ["ab", "cd"]
    assert rig.events[-1]["state"] == "done"



def test_first_llm_token_published_before_slow_second_token(rig):
    """The browser may show meaningful streamed text without waiting for token #2."""
    release_second = asyncio.Event()
    first_token_visible = asyncio.Event()

    async def generate(**kwargs):
        yield "Hallo"
        await release_second.wait()
        yield " zurück!"

    rig.stream.side_effect = generate
    original = rig.service.turn_engine.responses.emit_token

    async def capture_first(session_id, run_id, token):
        await original(session_id, run_id, token)
        if token == "Hallo":
            first_token_visible.set()

    rig.service.turn_engine.responses.emit_token = capture_first

    async def scenario():
        task = asyncio.create_task(rig.service.start_run("session", "run", "Erzähl mir etwas über Sterne"))
        await asyncio.wait_for(first_token_visible.wait(), timeout=1)
        assert [event["token"] for event in rig.events if event["event"] == "token"] == ["Hallo"]
        assert "done" not in event_order(rig)
        release_second.set()
        await task
        assert [event["token"] for event in rig.events if event["event"] == "token"] == [
            "Hallo", " zurück!"
        ]
        assert rig.events[-1]["state"] == "done"

    asyncio.run(scenario())


@pytest.mark.parametrize("utterance,tool_name,expected_fields", [
    ("Musik anhalten", "music_control", {"action": "pause"}),
    ("Musik fortsetzen", "music_control", {"action": "play"}),
    ("Stoppe die Musik", "music_control", {"action": "pause"}),
    ("Offene Erinnerungen", "reminder_list", {}),
    ("Kommende Termine", "calendar_list_events", {}),
    ("Verfasse eine Mail", "mail_create_draft", {}),
    ("Erzeuge eine Notiz", "notes_create", {}),
    ("Zwischenablage lesen", "clipboard_read", {}),
    ("raycast befehl raycast/file-search/search-files mit text ~/Desktop",
     "raycast_run_command", {"owner": "raycast", "extension": "file-search", "command": "search-files"}),
])
def test_review_legacy_command_must_wait_for_explicit_tool_approval(
    rig, utterance, tool_name, expected_fields,
):
    async def check():
        await rig.service.start_run("session", "run", utterance)
        assert event_order(rig) == ["received", "thinking", "approval_required"]
        approvals = await rig.db.list_pending_approvals()
        assert len(approvals) == 1
        assert approvals[0]["tool_name"] == tool_name
        for key, value in expected_fields.items():
            assert approvals[0]["tool_input"][key] == value
        assert rig.events[-1]["data"]["approval"] == approvals[0]
        rig.tools.execute.assert_not_awaited()
        rig.planner.assert_not_awaited()
        rig.stream.assert_not_called()

    asyncio.run(check())


@pytest.mark.parametrize("utterance", [
    "Ich möchte über meine Erinnerungen sprechen.",
    "Erkläre mir, wie Notizen funktionieren.",
    "Warum sollte ich die Musik anhalten?",
    "Welche Möglichkeiten bietet Raycast?",
    "Mach es kürzer.",
    "Erklär mir das einfacher.",
    "Ich möchte über Dateien reden.",
])
def test_review_conversation_never_creates_approval_or_executes(rig, utterance):
    rig.set_stream(["Eine normale Antwort."])

    async def check():
        await rig.service.start_run("session", "run", utterance)
        assert event_order(rig) == ["received", "thinking", "token", "message", "done"]
        assert await rig.db.list_pending_approvals() == []
        rig.tools.execute.assert_not_awaited()
        rig.planner.assert_not_awaited()

    asyncio.run(check())


def test_learned_command_wins_over_heuristic_and_planner(rig):
    rig.service = rig.enable("JARVIS_ENABLE_TOOL_PLANNER")

    async def check():
        await rig.db.upsert_learned_command(
            trigger="oeffne Safari", tool_name="open_app", tool_input={"app_name": "Notes"},
        )
        await rig.service.start_run("session", "run", "oeffne Safari")
        assert rig.events[-1]["data"]["approval"]["tool_input"] == {"app_name": "Notes"}
        rig.planner.assert_not_awaited()
        rig.tools.execute.assert_not_awaited()

    asyncio.run(check())


def test_prompt_keeps_memory_learning_signals_and_filters_non_conversation_roles(rig):
    rig.set_stream(["Antwort"])

    async def check():
        await rig.db.add_memory_item("session", "Sterne sind wichtig", 0.9)
        await rig.db.record_tool_learning(tool_name="open_app", success=True, latency_ms=42)
        await rig.db.add_message(session_id="session", role="tool", content="not conversation")
        await rig.db.add_message(session_id="session", role="assistant", content="earlier answer")
        await rig.service.start_run("session", "run", "Sterne")
        messages = rig.stream.call_args.kwargs["messages"]
        assert "- Sterne sind wichtig" in messages[0]["content"]
        assert "- open_app: 100% Erfolg, 42 ms Durchschnitt" in messages[0]["content"]
        assert messages[1:] == [
            {"role": "assistant", "content": "earlier answer"},
            {"role": "user", "content": "Sterne"},
        ]

    asyncio.run(check())


@pytest.mark.parametrize("kind", ["reply", "intent", "conversation"])
def test_routing_can_be_replaced_without_replacing_lifecycle(rig, kind):
    from jarvis_agent.orchestration.legacy_routing import LegacyRoute
    from jarvis_agent.tool_intent import ToolCallIntent

    # Deliberately use text which the legacy router would reject. The engine
    # must coordinate the supplied result, not run a second hidden router.
    result = {
        "reply": LegacyRoute("effective", reply="Injected response", detail="Injected route"),
        "intent": LegacyRoute("effective", intent=ToolCallIntent("open_app", {"app_name": "Safari"}, "injected")),
        "conversation": LegacyRoute("effective"),
    }[kind]
    route = AsyncMock(return_value=result)
    rig.service.turn_engine.routing = SimpleNamespace(route=route)
    rig.set_stream(["Conversation"])

    async def check():
        await rig.service.start_run("session", "run", "mach xyz")
        route.assert_awaited_once()
        assert route.call_args.args[:3] == ("session", "run", "mach xyz")
        assert event_order(rig)[:2] == ["received", "thinking"]
        if kind == "intent":
            assert event_order(rig)[2:] == ["approval_required"]
            assert len(await rig.db.list_pending_approvals()) == 1
        else:
            assert event_order(rig)[-2:] == ["message", "done"]
            assert rig.events[-2]["content"] == ("Injected response" if kind == "reply" else "Conversation")
        rig.tools.execute.assert_not_awaited()

    asyncio.run(check())
