"""Legacy routing characterization: priority collisions and German golden inputs."""

import asyncio
import ast
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from jarvis_agent.conversation_helpers import looks_like_tool_request
from jarvis_agent.db import Database
from jarvis_agent.learning_engine import LearningEngine
from jarvis_agent.orchestration import legacy_planner as planner_module
from jarvis_agent.orchestration import legacy_routing as routing_module
from jarvis_agent.orchestration import routing_stages as stages_module
from jarvis_agent.tool_intent import ToolCallIntent, infer_heuristic_tool_call
from jarvis_agent.tools import ToolRegistry


@pytest.fixture
def router(tmp_path, monkeypatch):
    db = Database(tmp_path / "routing.db", tmp_path, tmp_path / "model.bin")
    asyncio.run(db.init())
    tools = ToolRegistry()
    learning = LearningEngine(db, tools)
    responses = SimpleNamespace(emit_state=AsyncMock())
    planner = AsyncMock(return_value={
        "tool_name": "open_app", "tool_input": {"app_name": "Notes"}, "reason": "planner",
    })
    monkeypatch.setattr(planner_module, "plan_tool_call", planner)
    monkeypatch.setattr(planner_module.semantic_pilot, "supported_legacy_platform", lambda: True)
    routing = routing_module.LegacyRouting(tools, learning, responses, enable_tool_planner=True)
    return SimpleNamespace(db=db, routing=routing, learning=learning, responses=responses, planner=planner)


def route(router, message, profile=None):
    return asyncio.run(router.routing.route("session", "run", message, profile or {}, {}))


ORDER = ["block", "confirm", "learning", "quick", "status", "utility", "clarification",
         "learned", "heuristic", "planner"]


@pytest.mark.parametrize("winner", ORDER)
def test_first_matching_stage_wins_even_when_all_later_stages_match(router, monkeypatch, winner):
    visited = []
    intent = ToolCallIntent("open_app", {"app_name": "Safari"}, "deterministic")

    def candidate(name, value):
        def match(*args, **kwargs):
            visited.append(name)
            return value if ORDER.index(name) >= ORDER.index(winner) else None
        return match

    for name, function in [
        ("block", "detect_blocked_user_request"), ("confirm", "detect_confirmation_required_request"),
        ("quick", "quick_local_reply"), ("status", "quick_system_status_reply"),
        ("utility", "quick_utility_reply"), ("clarification", "quick_clarification_reply"),
        ("heuristic", "infer_heuristic_tool_call"),
    ]:
        monkeypatch.setattr(stages_module, function, candidate(name, intent if name == "heuristic" else name))
    monkeypatch.setattr(router.learning, "handle_learning_instruction",
                        AsyncMock(side_effect=candidate("learning", "learning")))
    monkeypatch.setattr(router.learning, "resolve_learned_command_intent",
                        AsyncMock(side_effect=candidate("learned", intent)))
    from jarvis_agent.orchestration.semantic_pilot import SemanticDecision

    router.routing.planner.plan = AsyncMock(side_effect=candidate(
        "planner",
        SemanticDecision("tool", ToolCallIntent("open_app", {"app_name": "Notes"}, "planner")),
    ))
    result = route(router, "mach xyz")
    assert visited == ORDER[:ORDER.index(winner) + 1]
    if winner in {"learned", "heuristic", "planner"}:
        assert result.reply is None
        assert result.intent.tool_name == "open_app"
        assert result.intent.tool_input == {"app_name": "Notes" if winner == "planner" else "Safari"}
    else:
        assert result.intent is None
        assert winner in result.reply
    router.responses.emit_state.assert_not_awaited()


@pytest.mark.parametrize("message, safety, detail", [
    ("hallo jarvis", {"blocked_request_patterns": ["hallo"], "confirmation_required_patterns": ["hallo"]},
     "Sicherheitsregel hat Anfrage blockiert"),
    ('/learn "fokus" => oeffne Safari', {"confirmation_required_patterns": ["Safari"]},
     "Sicherheitsbestaetigung erforderlich"),
    ("oeffne Safari", {"confirmation_required_patterns": ["Safari"]}, "Sicherheitsbestaetigung erforderlich"),
    ('/learn "fokus" => oeffne Safari', {}, "Lernmodus aktualisiert"),
    ("hallo jarvis", {}, "Schnellantwort lokal"),
    ("mach mir eine erinnerung", {}, "Rueckfrage fuer praezisen Auftrag"),
])
def test_real_priority_collisions(router, message, safety, detail):
    result = route(router, message, {"safety": safety})
    assert result.detail == detail
    assert result.reply and result.intent is None
    router.planner.assert_not_awaited()
    if detail == "Sicherheitsbestaetigung erforderlich":
        assert asyncio.run(router.db.list_learned_commands()) == []



@pytest.mark.parametrize("message,tool_name,expected_input", [
    ("Jarvis, öffne Safari", "open_app", {"app_name": "Safari"}),
    ("Jarvis, oeffne Safari", "open_app", {"app_name": "Safari"}),
    ("Lies diese Datei", None, None),
    ("datei lesen /tmp/test.txt", "file_read", {"path": "/tmp/test.txt"}),
    ("zeige erinnerungen 6", "reminder_list", {"limit": 6}),
])
def test_no_keyword_collision_with_actual_tool_intents(router, message, tool_name, expected_input):
    result = route(router, message)
    assert result.detail != "Utility-Antwort lokal"
    assert result.intent is not None if tool_name else result.intent is None
    if tool_name:
        assert result.intent.tool_name == tool_name
        assert result.intent.tool_input == expected_input
    else:
        assert result.reply == "Welche Datei soll ich lesen?"
    router.planner.assert_not_awaited()


@pytest.mark.parametrize("message", [
    "Ich möchte über Dateien sprechen",
    "Ich möchte über meine Erinnerungen sprechen",
    "Erklär mir das einfacher",
    "Mach es kürzer",
    "Und was wäre die Alternative?",
    "Warum?",
])
def test_conversation_is_not_misclassified_as_tool_action(router, message):
    result = route(router, message)
    assert result.intent is None
    assert result.reply is None
    router.planner.assert_not_awaited()


@pytest.mark.parametrize("message,answer", [
    ("Wie spät ist es?", "Uhr"),
    ("Welches Datum haben wir?", "Heute ist"),
    ("Bist du da?", "bin da"),
])
def test_explicit_utility_queries_bypass_planner(router, message, answer):
    result = route(router, message)
    assert result.detail == "Utility-Antwort lokal"
    assert answer.lower() in result.reply.lower()
    router.planner.assert_not_awaited()


def test_unknown_explicit_tool_never_falls_through_to_planner(router):
    result = route(router, '/tool unknown {"value":"oeffne Safari"}')
    assert result.intent is None
    assert result.detail == "Tool-Aufruf unklar, keine Ausfuehrung"
    router.planner.assert_not_awaited()


def test_reminder_with_content_asks_only_for_missing_time(router):
    result = route(router, "Erinnere mich an den Einkauf.")
    assert result.reply == "Wann soll ich dich daran erinnern?"
    assert result.detail == "Rueckfrage fuer praezisen Auftrag"
    router.planner.assert_not_awaited()

# One concrete utterance for every registered legacy ToolRegistry intent, plus
# multiple accepted forms of music control. This catches divergence between
# looks_like_tool_request() and infer_heuristic_tool_call() before it reaches CI.
LEGACY_INTENT_CASES = [
    ("Bitte oeffne https://example.com jetzt", "open_url", {"url": "https://example.com"}),
    ("öffne Safari bitte", "open_app", {"app_name": "Safari"}),
    ("oeffne raycast mit suche projekt status", "raycast_open", {}),
    ("raycast befehl raycast/file-search/search-files mit text ~/Desktop",
     "raycast_run_command", {"owner": "raycast", "extension": "file-search", "command": "search-files"}),
    ("Zwischenablage lesen", "clipboard_read", {}),
    ("kopiere Hallo Sir in die Zwischenablage", "clipboard_write", {"text": "Hallo Sir"}),
    ("erinner mich morgen 8 uhr an den muell", "reminder_create", {}),
    ("Offene Erinnerungen", "reminder_list", {}),
    ("plane morgen 09:30 uhr einen termin fuer 45 minuten mit titel Daily Standup",
     "calendar_create_event", {}),
    ("Kommende Termine", "calendar_list_events", {}),
    ("Erzeuge eine Notiz", "notes_create", {}),
    ("suche in notizen nach projekt phoenix 5", "notes_search", {}),
    ("Verfasse eine Mail", "mail_create_draft", {}),
    ("sende nachricht an +49123456789: Bitte Licht ausmachen", "messages_send", {}),
    ("suche kontakt Max Mustermann", "contacts_search", {}),
    ("Musik anhalten", "music_control", {"action": "pause"}),
    ("Musik fortsetzen", "music_control", {"action": "play"}),
    ("Stoppe die Musik", "music_control", {"action": "pause"}),
    ("Musik nächster Titel", "music_control", {"action": "next"}),
    ("Musik zurück", "music_control", {"action": "previous"}),
    ("datei lesen /tmp/test.txt", "file_read", {"path": "/tmp/test.txt"}),
    ("datei schreiben /tmp/test.txt: Hallo", "file_write", {"path": "/tmp/test.txt"}),
]


def test_review_matrix_covers_all_registered_legacy_tool_intents(router):
    expected = {tool_name for _, tool_name, _ in LEGACY_INTENT_CASES}
    registered = {spec["tool_name"] for spec in router.routing.heuristic.tools.list_specs()}
    assert expected == registered


@pytest.mark.parametrize("utterance,tool_name,fields", LEGACY_INTENT_CASES)
def test_every_supported_legacy_heuristic_passes_conversation_gate(router, utterance, tool_name, fields):
    existing = infer_heuristic_tool_call(utterance)
    assert existing is not None, f"Not actually supported by existing heuristic: {utterance}"
    assert existing.tool_name == tool_name
    assert looks_like_tool_request(utterance), f"Gate dropped {tool_name}: {utterance}"

    result = route(router, utterance)
    assert result.reply is None
    assert result.intent is not None
    assert result.intent.tool_name == tool_name
    for key, value in fields.items():
        assert existing.tool_input[key] == value
        assert result.intent.tool_input[key] == value
    router.planner.assert_not_awaited()


def test_newly_reachable_music_command_still_respects_learned_override(router):
    asyncio.run(router.db.upsert_learned_command(
        trigger="Musik anhalten", tool_name="open_app", tool_input={"app_name": "Notes"},
    ))
    result = route(router, "Musik anhalten")
    assert result.intent == ToolCallIntent(
        "open_app", {"app_name": "Notes"},
        "Gelernter Befehl: musik anhalten", "musik anhalten",
    )
    router.planner.assert_not_awaited()


def test_newly_reachable_command_still_obeys_safety_before_heuristics(router):
    blocked = route(router, "Musik anhalten", {
        "safety": {"blocked_request_patterns": ["Musik anhalten"]}
    })
    assert blocked.detail == "Sicherheitsregel hat Anfrage blockiert"
    assert blocked.intent is None
    confirmed = route(router, "Musik anhalten", {
        "safety": {"confirmation_required_patterns": ["Musik anhalten"]}
    })
    assert confirmed.detail == "Sicherheitsbestaetigung erforderlich"
    assert confirmed.intent is None
    router.planner.assert_not_awaited()


@pytest.mark.parametrize("utterance", [
    "Ich möchte über meine Erinnerungen sprechen.",
    "Erkläre mir, wie Notizen funktionieren.",
    "Warum sollte ich die Musik anhalten?",
    "Welche Möglichkeiten bietet Raycast?",
    "Mach es kürzer.",
    "Erklär mir das einfacher.",
    "Ich möchte über Dateien reden.",
])
def test_review_discussion_phrases_are_never_interpreted_as_actions(router, utterance):
    assert not looks_like_tool_request(utterance)
    result = route(router, utterance)
    assert result.intent is None
    assert result.reply is None
    router.planner.assert_not_awaited()


@pytest.mark.parametrize("message, tool_name, tool_input", [
    ("öffne Safari bitte", "open_app", {"app_name": "Safari"}),
    ("kannst du bitte Safari öffnen", "open_app", {"app_name": "Safari"}),
    ("oeffne die notiz app", "open_app", {"app_name": "Notes"}),
    ("Bitte oeffne https://example.com jetzt", "open_url", {"url": "https://example.com"}),
    ('/tool file_read {"path":"/tmp/test.txt"}', "file_read", {"path": "/tmp/test.txt"}),
    ("kopiere Hallo Sir in die Zwischenablage", "clipboard_write", {"text": "Hallo Sir"}),
    ("musik pausieren", "music_control", {"action": "pause"}),
    ('/tool reminder_list {"limit":6}', "reminder_list", {"limit": 6}),
])
def test_german_heuristic_golden_arguments_precede_planner(router, message, tool_name, tool_input):
    result = route(router, message)
    assert result.reply is None
    assert result.intent.tool_name == tool_name
    assert result.intent.tool_input == tool_input
    assert result.intent.source_trigger is None
    router.planner.assert_not_awaited()


@pytest.mark.parametrize("message", ["oeffne Safari", "Jarvis, oeffne Safari bitte jetzt"])
def test_learned_trigger_overrides_heuristic_with_exact_arguments(router, message):
    asyncio.run(router.db.upsert_learned_command(
        trigger="oeffne Safari", tool_name="open_app", tool_input={"app_name": "Notes"},
    ))
    result = route(router, message)
    assert result.intent == ToolCallIntent("open_app", {"app_name": "Notes"},
                                          "Gelernter Befehl: oeffne safari", "oeffne safari")
    router.planner.assert_not_awaited()


def test_learning_commands_keep_nonrecursive_action_resolution_and_unlearn(router):
    asyncio.run(router.db.upsert_learned_command(
        trigger="oeffne Safari", tool_name="open_app", tool_input={"app_name": "Notes"},
    ))
    assert route(router, '/learn "fokus" => oeffne Safari').detail == "Lernmodus aktualisiert"
    assert route(router, "fokus").intent.tool_input == {"app_name": "Safari"}
    assert "`fokus` -> `open_app`" in route(router, "/learn-list").reply
    assert route(router, '/unlearn "fokus"').reply == "Gelerntes Kommando entfernt: `fokus`."
    assert route(router, "fokus").intent is None
    router.planner.assert_not_awaited()


@pytest.mark.parametrize("learned", [False, True])
def test_adaptive_routing_preserves_arguments_and_source_trigger(router, learned):
    async def prepare():
        for _ in range(3):
            await router.db.record_tool_learning(tool_name="raycast_open", success=True, latency_ms=10)
        if learned:
            await router.db.upsert_learned_command(
                trigger="fokus", tool_name="open_app", tool_input={"app_name": "Raycast"},
            )
    asyncio.run(prepare())
    result = route(router, "fokus" if learned else "oeffne Raycast")
    assert result.intent.tool_name == "raycast_open"
    assert result.intent.tool_input == {"fallback_text": ""}
    assert result.intent.source_trigger == ("fokus" if learned else None)
    router.planner.assert_not_awaited()


@pytest.mark.parametrize("enabled", [False, True])
def test_planner_failure_clarifies_tool_request_but_conversation_does_not_plan(router, enabled):
    router.routing.planner.enable_tool_planner = enabled
    router.planner.return_value = None
    unclear = route(router, "mach xyz")
    assert unclear.detail == "Tool-Aufruf unklar, keine Ausfuehrung"
    assert unclear.intent is None and "nicht eindeutig erkannt" in unclear.reply
    assert router.planner.await_count == int(enabled)
    router.planner.reset_mock()
    conversation = route(router, "Erzaehle etwas ueber Sterne")
    assert conversation == routing_module.LegacyRoute("Erzaehle etwas ueber Sterne")
    router.planner.assert_not_awaited()


def test_confirmation_state_and_event_timing_survive_later_failure(router, monkeypatch):
    profile = {"safety": {"confirmation_required_patterns": ["Safari"]}}
    assert route(router, "Bestaetige", profile).user_message == "Bestaetige"
    router.responses.emit_state.assert_not_awaited()
    assert route(router, "oeffne Safari", profile).detail == "Sicherheitsbestaetigung erforderlich"
    assert router.routing.pending_confirmations["session"]["original_message"] == "oeffne Safari"

    async def fail_after_confirmation(**kwargs):
        assert kwargs["user_message"] == "oeffne Safari"
        assert "session" not in router.routing.pending_confirmations
        router.responses.emit_state.assert_awaited_once_with(
            session_id="session", run_id="run", state="thinking", detail="Sicherheitsbestaetigung akzeptiert",
        )
        raise RuntimeError("learning unavailable")
    monkeypatch.setattr(router.learning, "handle_learning_instruction", fail_after_confirmation)
    with pytest.raises(RuntimeError, match="learning unavailable"):
        route(router, "Bestaetige", profile)


@pytest.mark.parametrize("pending, message, restored, accepted", [
    (False, "Bestaetige", "Bestaetige", False),
    (True, "Bestaetige", "oeffne Safari", True),
    (True, "hallo jarvis", "hallo jarvis", False),
])
def test_safety_stage_returns_confirmation_metadata_without_lifecycle_dependencies(pending, message, restored, accepted):
    safety = stages_module.LegacySafetyStage()
    profile = {"safety": {"confirmation_required_patterns": ["Safari"]}}
    if pending:
        initial = safety.resolve_confirmation("session", "oeffne Safari", profile)
        assert safety.check("session", initial, profile).detail == "Sicherheitsbestaetigung erforderlich"
    safety.pending_confirmations["other"] = {"original_message": "untouched"}
    result = safety.resolve_confirmation("session", message, profile)
    assert result == stages_module.ConfirmationResolution(restored, accepted)
    assert safety.pending_confirmations == {"other": {"original_message": "untouched"}}
    assert safety.check("session", result, profile) is None


def test_confirmation_never_bypasses_hard_block_and_event_precedes_check(router, monkeypatch):
    router.routing.pending_confirmations["session"] = {"original_message": "oeffne Safari"}

    def block(message, profile):
        assert message == "oeffne Safari"
        router.responses.emit_state.assert_awaited_once()
        return "new hard block"
    monkeypatch.setattr(stages_module, "detect_blocked_user_request", block)
    assert route(router, "Bestaetige").detail == "Sicherheitsregel hat Anfrage blockiert"
    router.planner.assert_not_awaited()


@pytest.mark.parametrize("enabled", [False, True])
def test_unregistered_heuristic_reaches_only_enabled_legacy_planner(router, enabled):
    router.routing.planner.enable_tool_planner = enabled
    result = route(router, '/tool unknown {"value":1}')
    assert result.intent is None
    assert result.detail == "Tool-Aufruf unklar, keine Ausfuehrung"
    router.planner.assert_not_awaited()
    result = route(router, '/tool unknown {"value":"oeffne"}')
    assert result.intent is None
    assert result.detail == "Tool-Aufruf unklar, keine Ausfuehrung"
    router.planner.assert_not_awaited()


def test_learn_action_retains_existing_planner_callback(router):
    # A new learned command must be grounded in a deterministic action, not
    # persisted from an unverified semantic fallback.
    result = route(router, '/learn "fokus" => oeffne Safari')
    assert result.detail == "Lernmodus aktualisiert"
    router.planner.assert_not_awaited()
    assert route(router, "fokus").intent.tool_input == {"app_name": "Safari"}
    router.planner.assert_not_awaited()


def test_stage_module_has_no_lifecycle_model_or_platform_imports():
    tree = ast.parse(inspect.getsource(stages_module))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not imports & {"events", "legacy_responses", "turn_engine", "llm", "os", "sys", "subprocess"}
    assert not any(isinstance(node, ast.Attribute) and node.attr in {"emit_state", "publish", "stream_response"}
                   for node in ast.walk(tree))
