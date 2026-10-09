"""YJCOM-03: real facts reach the model; only the model owns visible prose."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from jarvis_agent.llm import LlmError, ModelToolCall
from jarvis_agent.runtime_facts import (
    DISCOVERY_TOOL, LOCAL_TIME_TOOL, ReadOnlyToolkit,
)
from jarvis_agent.orchestration import legacy_responses as response_module
from test_turn_lifecycle import event_order, rig


@pytest.mark.parametrize("message,reply", [
    ("Hallo, Jarvis", "Guten Abend!"),
    ("Hallo, Jarvis", "Schön, dass du da bist."),
    ("Danke, Jarvis", "Sehr gern."),
    ("Danke, Jarvis", "Immer gerne!"),
    ("Bist du da?", "Ja, ich höre zu."),
    ("Okay.", "Alles verstanden."),
    ("Was machen wir als Nächstes?", "Wir können am offenen Problem weiterarbeiten."),
    ("Welches Modell nutzt du?", "Das Modell wird im lokalen Backend konfiguriert."),
])
def test_normal_conversation_has_one_real_llm_stream_and_no_canned_answer(rig, message, reply):
    rig.set_stream([reply[:5], reply[5:]])

    async def scenario():
        await rig.service.start_run("session", "run", message)
        assert rig.events[-2]["content"] == reply
        assert rig.events[-1]["state"] == "done"
        assert rig.stream.call_count == 1
        assert set(rig.stream.call_args.kwargs) == {"base_url", "model", "messages", "tools"}
        tools = rig.stream.call_args.kwargs["tools"]
        assert {t["function"]["name"] for t in tools} == {LOCAL_TIME_TOOL, DISCOVERY_TOOL}
        prompt = rig.stream.call_args.kwargs["messages"]
        assert prompt[-1] == {"role": "user", "content": message}
        assert [row["content"] for row in prompt if row["role"] == "user"] == [message]
        rig.planner.assert_not_awaited()
        rig.tools.execute.assert_not_awaited()
        assert await rig.db.list_pending_approvals() == []

    asyncio.run(scenario())


def test_followup_uses_actual_session_history_and_one_model_call(rig):
    rig.set_stream(["Daraus folgt eine Erklärung."])

    async def scenario():
        await rig.db.add_message(session_id="session", role="user", content="Sprechen wir über das Projekt.")
        await rig.db.add_message(session_id="session", role="assistant", content="Wir müssen den Fehler beheben.")
        await rig.service.start_run("session", "run", "Warum?")
        messages = rig.stream.call_args.kwargs["messages"]
        assert messages[-3:] == [
            {"role": "user", "content": "Sprechen wir über das Projekt."},
            {"role": "assistant", "content": "Wir müssen den Fehler beheben."},
            {"role": "user", "content": "Warum?"},
        ]
        assert rig.stream.call_count == 1
        assert rig.events[-2]["content"] == "Daraus folgt eine Erklärung."

    asyncio.run(scenario())


@pytest.mark.parametrize("message,reply", [
    ("Jarvis, wie spät ist es?", "Es ist bei dir gerade 17:23 Uhr."),
    ("Welches Datum haben wir?", "Heute ist Freitag, der 9. Oktober."),
])
def test_local_datetime_only_from_structured_runtime_and_model_reply(rig, message, reply):
    frozen = datetime(2026, 10, 9, 17, 23, 5, tzinfo=timezone(timedelta(hours=2), "CEST"))
    toolkit = ReadOnlyToolkit(rig.tools, clock=lambda: frozen, platform_name="win32")
    rig.service.turn_engine.responses.read_only_toolkit = toolkit
    received = []

    async def model(**kwargs):
        received.append(kwargs)
        if "tools" in kwargs:
            yield ModelToolCall(LOCAL_TIME_TOOL, {})
        else:
            assert kwargs["messages"][-2]["role"] == "assistant"
            tool_result = kwargs["messages"][-1]
            assert tool_result["role"] == "tool"
            assert tool_result["tool_name"] == LOCAL_TIME_TOOL
            data = json.loads(tool_result["content"])
            assert data["local_iso"] == "2026-10-09T17:23:05+02:00"
            assert data["local_date"] == "2026-10-09"
            assert data["timezone_label"] == "CEST"
            assert data["utc_offset"] == "+02:00"
            yield reply

    rig.stream.side_effect = model

    async def scenario():
        await rig.service.start_run("session", "run", message)
        assert len(received) == 2
        assert rig.events[-2]["content"] == reply
        assert rig.events[-1]["state"] == "done"
        assert event_order(rig) == ["received", "thinking", "token", "message", "done"]
        assert (await rig.db.list_messages("session"))[-1]["content"] == reply
        assert len(await rig.db.list_pending_approvals()) == 0
        rig.tools.execute.assert_not_awaited()

    asyncio.run(scenario())


def test_capability_snapshot_is_derived_from_actual_registry_and_sent_to_model(rig):
    rig.service.turn_engine.responses.read_only_toolkit = ReadOnlyToolkit(
        rig.tools, platform_name="win32", command_exists=lambda name: None,
    )
    seen = []

    async def model(**kwargs):
        seen.append(kwargs)
        if "tools" in kwargs:
            yield ModelToolCall(DISCOVERY_TOOL, {})
        else:
            data = json.loads(kwargs["messages"][-1]["content"])
            assert data["platform"] == "win32"
            assert "open_app" in {x["name"] for x in data["legacy_registered"]}
            assert not next(x for x in data["legacy_registered"] if x["name"] == "open_app")["available"]
            assert data["v2_catalog"]["available_for_execution"] == []
            yield "Ich kann die lokale Zeit prüfen; macOS-App-Steuerung steht hier nicht zur Verfügung."

    rig.stream.side_effect = model

    async def scenario():
        await rig.service.start_run("session", "run", "Welche Systemfunktionen kannst du gerade verwenden?")
        assert len(seen) == 2
        assert rig.events[-2]["content"].startswith("Ich kann die lokale Zeit")
        rig.tools.execute.assert_not_awaited()
        assert await rig.db.list_pending_approvals() == []

    asyncio.run(scenario())


@pytest.mark.parametrize("message,first", [
    ("Wie spät ist es?", ["Die Uhr zeigt angeblich 12:00 Uhr."]),
    ("Welches Datum haben wir?", []),
    ("Welche Systemfunktionen kannst du verwenden?", ["Du kannst alles kontrollieren."]),
])
def test_live_fact_claim_without_verified_tool_is_error_not_fake_message(rig, message, first):
    rig.set_stream(first)

    async def scenario():
        await rig.service.start_run("session", "run", message)
        assert event_order(rig) == ["received", "thinking", "message", "error"]
        assert "nicht verifiziert" in rig.events[-2]["content"]
        assert rig.stream.call_count == 1
        rig.tools.execute.assert_not_awaited()
        assert await rig.db.list_pending_approvals() == []

    asyncio.run(scenario())


@pytest.mark.parametrize("proposal", [
    ModelToolCall("open_app", {"app_name": "Safari"}),
    ModelToolCall("file_write", {"path": "/tmp/x", "content": "hi"}),
    ModelToolCall(LOCAL_TIME_TOOL, {"shell": "echo hi"}),
    ModelToolCall("unknown.tool", {}),
])
def test_model_cannot_execute_legacy_action_or_unknown_fact_tool(rig, proposal):
    async def model(**kwargs):
        yield proposal

    rig.stream.side_effect = model

    async def scenario():
        await rig.service.start_run("session", "run", "Hallo")
        assert rig.events[-1]["state"] == "error"
        rig.tools.execute.assert_not_awaited()
        assert await rig.db.list_pending_approvals() == []

    asyncio.run(scenario())


def test_mixed_fabricated_text_and_tool_call_is_fail_closed(rig):
    async def model(**kwargs):
        yield "Es ist 12 Uhr."
        yield ModelToolCall(LOCAL_TIME_TOOL, {})

    rig.stream.side_effect = model

    async def scenario():
        await rig.service.start_run("session", "run", "Wie spät ist es?")
        assert event_order(rig) == ["received", "thinking", "message", "error"]
        rig.tools.execute.assert_not_awaited()

    asyncio.run(scenario())


def test_llm_transport_failure_is_visible_and_never_pretends_success(rig):
    rig.set_stream([], LlmError("offline"))
    asyncio.run(rig.service.start_run("session", "run", "Hallo"))
    assert rig.events[-1]["state"] == "error"
    assert "offline" in rig.events[-2]["content"]
    rig.tools.execute.assert_not_awaited()
