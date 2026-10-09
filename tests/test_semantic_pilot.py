"""YJCOM-02: model proposals stay behind deterministic validation and approval."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from jarvis_agent import llm
from jarvis_agent.orchestration import legacy_planner, semantic_pilot
from jarvis_agent.tools import ToolRegistry


@pytest.fixture
def pilot(monkeypatch):
    monkeypatch.setattr(semantic_pilot, "supported_legacy_platform", lambda: True)
    model = AsyncMock(return_value={"decision": "conversation"})
    monkeypatch.setattr(legacy_planner, "plan_tool_call", model)
    learning = SimpleNamespace(rank_tool_specs_for_planner=AsyncMock(
        side_effect=lambda specs: specs,
    ))
    tools = ToolRegistry()
    adapter = legacy_planner.LegacyPlannerAdapter(
        tools, learning, enable_tool_planner=True,
    )
    return SimpleNamespace(model=model, learning=learning, tools=tools, adapter=adapter)


def test_opt_in_default_disabled_stays_without_model(pilot):
    pilot.adapter.enable_tool_planner = False
    assert asyncio.run(pilot.adapter.plan("Aktiviere bitte die App Safari", {})) is None
    pilot.model.assert_not_awaited()
    pilot.learning.rank_tool_specs_for_planner.assert_not_awaited()


@pytest.mark.parametrize("text", [
    "Danke, Jarvis", "Wie spät ist es?", "Erkläre mir, wie Apps funktionieren.",
    "Ich möchte über meine Erinnerungen sprechen.", "Mach es kürzer.",
    "Erzähl mir etwas über das Wetter.", '/tool unknown {"app_name":"Safari"}',
])
def test_small_talk_meta_discussion_and_explicit_unknown_tool_never_use_pilot(pilot, text):
    assert asyncio.run(pilot.adapter.plan(text, {})) is None
    pilot.model.assert_not_awaited()


def test_unsupported_platform_skips_semantic_tool_model(pilot, monkeypatch):
    monkeypatch.setattr(semantic_pilot, "supported_legacy_platform", lambda: False)
    assert asyncio.run(pilot.adapter.plan("Aktiviere bitte die App Safari", {})) is None
    pilot.model.assert_not_awaited()


@pytest.mark.parametrize("text,name,args,fields", [
    ("Aktiviere bitte die App Safari", "open_app", {"app_name": "Safari"}, {"app_name": "Safari"}),
    ("Gehe zu https://example.org/info", "open_url",
     {"url": "https://example.org/info"}, {"url": "https://example.org/info"}),
    ("Zeig mir bitte meine Erinnerungen", "reminder_list", {}, {"limit": 8}),
    ("Zeig mir bitte meine Termine", "calendar_list_events", {}, {"days_ahead": 7, "limit": 10}),
    ("Zeig mir meine Notizen zu Projekt Phoenix", "notes_search",
     {"query": "Projekt Phoenix", "limit": 8}, {"query": "Projekt Phoenix"}),
])
def test_allowlisted_grounded_single_tool_decision(pilot, text, name, args, fields):
    pilot.model.return_value = {"decision": "tool", "tool_name": name, "tool_input": args}
    decision = asyncio.run(pilot.adapter.plan(text, {}))
    assert decision is not None and decision.kind == "tool"
    assert decision.intent is not None and decision.intent.tool_name == name
    assert decision.intent.reason == "Validierter lokaler Semantic-Pilot"
    for key, value in fields.items():
        assert decision.intent.tool_input[key] == value
    pilot.model.assert_awaited_once()
    specs = pilot.model.call_args.kwargs["tool_specs"]
    assert len(specs) == 5
    assert {spec["tool_name"] for spec in specs} == semantic_pilot.PILOT_TOOL_NAMES
    assert all(spec["requires_approval"] is True for spec in specs)
    pilot.learning.rank_tool_specs_for_planner.assert_awaited_once()


@pytest.mark.parametrize("returned,utterance", [
    ({"decision": "tool", "tool_name": "open_app",
      "tool_input": {"app_name": "Chrome"}}, "Aktiviere bitte die App Safari"),
    ({"decision": "tool", "tool_name": "open_app",
      "tool_input": {"app_name": ""}}, "Aktiviere bitte die App Safari"),
    ({"decision": "tool", "tool_name": "open_url",
      "tool_input": {"url": "https://different.invalid"}}, "Gehe zu https://example.org"),
    ({"decision": "tool", "tool_name": "open_url",
      "tool_input": {"url": "javascript:alert(1)"}}, "Gehe zu https://example.org"),
    ({"decision": "tool", "tool_name": "notes_search",
      "tool_input": {"query": "Geheimnis"}}, "Zeig mir meine Notizen zu Projekt Phoenix"),
    ({"decision": "tool", "tool_name": "notes_search",
      "tool_input": {"query": "Projekt Phoenix", "limit": True}}, "Zeig mir meine Notizen zu Projekt Phoenix"),
    ({"decision": "tool", "tool_name": "reminder_list",
      "tool_input": {"limit": 200}}, "Zeig mir bitte meine Erinnerungen"),
    ({"decision": "tool", "tool_name": "calendar_list_events",
      "tool_input": {"days_ahead": 45}}, "Zeig mir bitte meine Termine"),
    ({"decision": "tool", "tool_name": "file_write",
      "tool_input": {"path": "/tmp/secret", "content": "hi"}}, "Schreib Datei /tmp/secret"),
    ({"decision": "tool", "tool_name": "messages_send",
      "tool_input": {"to": "X", "text": "hello"}}, "Sende Nachricht an X"),
    ({"decision": "tool", "tool_name": "unknown",
      "tool_input": {}}, "Aktiviere bitte die App Safari"),
    ({"decision": "tool", "tool_name": "open_app",
      "tool_input": {"app_name": "Safari", "shell": "rm -rf"}}, "Aktiviere bitte die App Safari"),
    ({"decision": "tool", "tool_name": "open_app",
      "tool_input": "Safari"}, "Aktiviere bitte die App Safari"),
    ({"decision": "tool", "tool_name": "open_app",
      "tool_input": {"app_name": "Safari"}, "reason": "certainty"}, "Aktiviere bitte die App Safari"),
    ({"decision": "clarify", "question": "Bitte schicke dein Passwort?"}, "Aktiviere bitte die App Safari"),
    ({"decision": "clarify", "question": "Ausführen."}, "Aktiviere bitte die App Safari"),
])
def test_invalid_or_hallucinated_output_cannot_create_tool_intent(pilot, returned, utterance):
    pilot.model.return_value = returned
    assert asyncio.run(pilot.adapter.plan(utterance, {})) is None
    pilot.model.assert_awaited_once()


def test_single_clarification_or_conversation_is_safe(pilot):
    pilot.model.return_value = {"decision": "clarify", "question": "Welche App möchtest du öffnen?"}
    clarify = asyncio.run(pilot.adapter.plan("Aktiviere bitte die App", {}))
    assert clarify.kind == "clarify"
    assert clarify.question == "Welche App möchtest du öffnen?"
    assert clarify.intent is None
    pilot.model.reset_mock()
    pilot.model.return_value = {"decision": "conversation"}
    conversation = asyncio.run(pilot.adapter.plan("Aktiviere bitte die App", {}))
    assert conversation.kind == "conversation"
    assert conversation.intent is None
    pilot.model.assert_awaited_once()


@pytest.mark.parametrize("failure", [RuntimeError("offline"), ValueError("invalid")])
def test_model_errors_fail_closed(pilot, failure):
    pilot.model.side_effect = failure
    assert asyncio.run(pilot.adapter.plan("Aktiviere bitte die App Safari", {})) is None
    pilot.model.assert_awaited_once()


def test_timeout_is_finite_and_allows_next_turn(pilot, monkeypatch):
    monkeypatch.setattr(legacy_planner, "SEMANTIC_TIMEOUT_SECONDS", 0.015)

    async def slow(**kwargs):
        await asyncio.sleep(5)

    pilot.model.side_effect = slow
    assert asyncio.run(pilot.adapter.plan("Aktiviere bitte die App Safari", {})) is None
    pilot.model.reset_mock()
    pilot.model.side_effect = None
    pilot.model.return_value = {"decision": "conversation"}
    assert asyncio.run(pilot.adapter.plan("Aktiviere bitte die App Safari", {})).kind == "conversation"


@pytest.mark.parametrize("raw,valid", [
    ('{"decision":"conversation"}', True),
    ('{"decision":"conversation","decision":"tool"}', False),
    ('{"decision":"tool","tool_name":"open_app","tool_input":{}} extra', False),
    (chr(96) * 3 + 'json\n{"decision":"conversation"}\n' + chr(96) * 3, False),
    ('{"decision":"tool","tool_input":{"limit":NaN}}', False),
    ('["conversation"]', False),
    ("not json", False),
])
def test_llm_accepts_only_bounded_unique_json_object(monkeypatch, raw, valid):
    call = AsyncMock(return_value=raw)
    monkeypatch.setattr(llm, "complete_chat", call)
    result = asyncio.run(llm.plan_tool_call(
        base_url="http://127.0.0.1:11434",
        model="test",
        user_message="Aktiviere bitte die App Safari",
        tool_specs=[{"tool_name": "open_app", "input_schema": {"app_name": "string"}}],
    ))
    assert (result is not None) == valid
    call.assert_awaited_once()
    assert call.call_args.kwargs["timeout_seconds"] == 8.0
    assert call.call_args.kwargs["temperature"] == 0.0
    prompt = call.call_args.kwargs["messages"]
    assert len(prompt) == 2 and prompt[-1]["content"] == "Aktiviere bitte die App Safari"
