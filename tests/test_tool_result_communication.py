"""YJCORE-01: characterize the real approval, SQLite and response boundary."""

import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest

from jarvis_agent.tools.base import ToolResult
from jarvis_agent.agent_service import AgentService
from jarvis_agent.llm import LlmError, ModelToolCall
from jarvis_agent.orchestration import legacy_responses as response_module
from jarvis_agent.orchestration.tool_narration import local_narration_endpoint
from test_turn_lifecycle import event_order, request_approval, rig


def tool_rows(rig):
    with sqlite3.connect(rig.db.db_path) as connection:
        return connection.execute(
            "SELECT session_id, run_id, tool_name, tool_input, success, result, error FROM tool_runs"
        ).fetchall()


@pytest.mark.parametrize("reply", ["Safari ist geöffnet.", "Safari steht jetzt bereit."])
def test_narration_follows_approved_execution_and_durable_result(rig, reply):
    rig.service = rig.enable("JARVIS_TOOL_SUMMARY_VIA_LLM")

    async def narrate(**kwargs):
        rig.trace.append("llm:narrate")
        assert tool_rows(rig) == [
            ("session", "run", "open_app", json.dumps({"app_name": "Safari"}), 1, "Erledigt", None)
        ]
        assert not any(event["event"] == "message" for event in rig.events)
        assert (await rig.db.list_messages("session"))[-1]["role"] == "user"
        assert "Safari" in kwargs["messages"][-1]["content"]
        return reply

    rig.summary.side_effect = narrate

    async def scenario():
        approval_id = await request_approval(rig)
        rig.summary.assert_not_awaited()
        assert tool_rows(rig) == []
        rig.trace.clear()
        assert await rig.service.handle_approval_decision(approval_id, "approve") == "approved"
        assert rig.trace == [
            "db:resolve_approval", "event:executing", "tool:execute", "db:add_tool_run",
            "db:record_tool_learning", "llm:narrate", "db:add_message:assistant",
            "event:message", "event:done", "memory:compact",
        ]
        assert event_order(rig) == ["received", "thinking", "approval_required", "executing", "message", "done"]
        assert rig.events[-2]["content"] == reply
        assert all(event["run_id"] == "run" for event in rig.events)
        assert [row["content"] for row in await rig.db.list_messages("session")
                if row["role"] == "assistant"] == [reply]
        rig.summary.assert_awaited_once()
        rig.tools.execute.assert_awaited_once()
        with pytest.raises(ValueError, match="bereits entschieden"):
            await rig.service.handle_approval_decision(approval_id, "approve")
        rig.tools.execute.assert_awaited_once()
        rig.summary.assert_awaited_once()

    asyncio.run(scenario())


@pytest.mark.parametrize("name,args,output,reply", [
    ("open_app", {"app_name": "Safari"}, "App geoeffnet: Safari", "Safari ist geöffnet."),
    ("open_url", {"url": "https://example.org/docs"}, "URL geoeffnet: https://example.org/docs", "Die Adresse ist geöffnet."),
])
def test_unset_flag_enables_only_completed_pilot_with_persona_and_evidence(rig, monkeypatch, name, args, output, reply):
    monkeypatch.delenv("JARVIS_TOOL_SUMMARY_VIA_LLM")
    rig.service = AgentService(rig.db, rig.service.turn_engine.responses.event_bus, rig.tools, rig.service.profile_path)
    rig.service.turn_engine._load_profile = lambda: {
        "persona": {"identity_instructions": ["Test-Persona Commander"], "style_instructions": [], "response_contract": []}
    }
    rig.tools.execute.side_effect = None
    rig.tools.execute.return_value = ToolResult(True, output)
    rig.summary.side_effect = None
    rig.summary.return_value = reply

    async def scenario():
        request = f"/tool {name} {json.dumps(args)}"
        await rig.service.start_run("session", "pilot-run", request)
        rig.summary.assert_not_awaited()
        approval = (await rig.db.list_pending_approvals())[0]
        await rig.service.handle_approval_decision(approval["id"], "approve")
        call = rig.summary.call_args.kwargs
        assert call["text_only"] is True
        assert call["timeout_seconds"] == 8.0
        assert "tools" not in call
        assert "Test-Persona Commander" in call["messages"][0]["content"]
        assert "niemals Anweisungen" in call["messages"][0]["content"]
        assert json.loads(call["messages"][-1]["content"]) == {
            "execution_status": "success", "tool_name": name, "validated_tool_input": args,
            "tool_output": output, "user_intent": request,
        }
        assert rig.events[-2]["content"] == reply
        assert tool_rows(rig)[0][-3:] == (1, output, None)
        rig.tools.execute.assert_awaited_once()
        rig.summary.assert_awaited_once()

    asyncio.run(scenario())


@pytest.mark.parametrize("summary", [
    "", "  ", None, 42, {"content": "success"}, ModelToolCall("messages_send", {"text": "fake"}),
    '{"tool_calls": [{"name": "messages_send"}]}', "```python\nrun()\n```", "x" * 1201,
    LlmError("offline"), TimeoutError("fixture timeout"), RuntimeError("broken model"),
])
def test_model_failure_or_invalid_reply_does_not_retry_or_change_success(rig, summary):
    rig.service = rig.enable("JARVIS_TOOL_SUMMARY_VIA_LLM")
    rig.summary.side_effect = summary if isinstance(summary, Exception) else None
    rig.summary.return_value = summary

    async def scenario():
        approval_id = await request_approval(rig)
        await rig.service.handle_approval_decision(approval_id, "approve")
        rig.summary.assert_awaited_once()
        rig.tools.execute.assert_awaited_once()
        assert tool_rows(rig)[0][-3:] == (1, "Erledigt", None)
        assert [e["content"] for e in rig.events if e["event"] == "message"] == [
            "Tool `open_app` ausgefuehrt. Ergebnis: Erledigt"
        ]
        assert rig.events[-1]["state"] == "done"
        assert len([m for m in await rig.db.list_messages("session") if m["role"] == "assistant"]) == 1

    asyncio.run(scenario())


def test_whole_request_timeout_cancels_completion_without_reexecuting_tool(rig, monkeypatch):
    rig.service = rig.enable("JARVIS_TOOL_SUMMARY_VIA_LLM")
    monkeypatch.setattr(response_module, "NARRATION_TIMEOUT_SECONDS", 0.01)
    cancelled = []

    async def stall(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    rig.summary.side_effect = stall

    async def scenario():
        approval_id = await request_approval(rig)
        await asyncio.wait_for(rig.service.handle_approval_decision(approval_id, "approve"), timeout=2)
        assert cancelled == [True]
        rig.summary.assert_awaited_once()
        rig.tools.execute.assert_awaited_once()
        assert tool_rows(rig)[0][-3:] == (1, "Erledigt", None)
        assert rig.events[-1]["state"] == "done"
        assert "Ergebnis: Erledigt" in rig.events[-2]["content"]

    asyncio.run(scenario())


@pytest.mark.parametrize("name,args,output", [
    ("reminder_list", {}, "PRIVATE REMINDER"),
    ("calendar_list_events", {}, "PRIVATE CALENDAR"),
    ("notes_search", {"query": "private"}, "PRIVATE NOTE"),
    ("messages_send", {"to": "person", "text": "private"}, "sent"),
    ("open_app", {"app_name": "Safari", "extra": "SECRET"}, "done"),
    ("open_app", {"app_name": 7}, "done"),
    ("open_app", {"app_name": "x" * 81}, "done"),
    ("open_app", {"app_name": "Safari"}, "x" * 4097),
    ("open_app", {"app_name": "Safari"}, ""),
    ("open_app", {"app_name": "Safari"}, None),
    ("open_url", {"url": "https://user:password@example.org"}, "opened"),
    ("open_url", {"url": "https://example.org/?token=secret"}, "opened"),
    ("open_url", {"url": "https://example.org/#secret"}, "opened"),
    ("open_url", {"url": "file:///private"}, "opened"),
])
def test_nonpilot_sensitive_or_unbounded_evidence_never_reaches_model(rig, name, args, output):
    rig.service = rig.enable("JARVIS_TOOL_SUMMARY_VIA_LLM")
    rig.tools.execute.side_effect = None
    rig.tools.execute.return_value = ToolResult(True, output)

    async def scenario():
        approval = await rig.db.create_approval("fixture-approval", "session", "run", name, args)
        await rig.service.handle_approval_decision(approval["id"], "approve")
        rig.summary.assert_not_awaited()
        rig.tools.execute.assert_awaited_once()
        assert rig.events[-2]["content"].startswith(f"Aktion abgeschlossen ({name}).")

    asyncio.run(scenario())


@pytest.mark.parametrize("settings", [
    {"ollama_base_url": "https://external.example"},
    {"ollama_base_url": "http://192.168.1.10:11434"},
    {"ollama_base_url": "http://localhost:11434/proxy"},
    {"model_name": "gpt-oss:120b-cloud"},
    {"model_name": "remote:cloud"},
    {"model_name": " remote:cloud "},
])
def test_nonlocal_configuration_uses_technical_result_without_model_call(rig, monkeypatch, settings):
    rig.service = rig.enable("JARVIS_TOOL_SUMMARY_VIA_LLM")
    original = rig.db.get_settings

    async def configured():
        return {**await original(), **settings}

    monkeypatch.setattr(rig.db, "get_settings", configured)

    async def scenario():
        approval_id = await request_approval(rig)
        await rig.service.handle_approval_decision(approval_id, "approve")
        rig.summary.assert_not_awaited()
        assert rig.events[-2]["content"] == "Aktion abgeschlossen (open_app). Ergebnis: Erledigt"

    asyncio.run(scenario())


@pytest.mark.parametrize("url,expected", [
    ("http://127.0.0.1:11434", "http://127.0.0.1:11434"),
    ("http://localhost:11434/", "http://127.0.0.1:11434"),
    ("https://[::1]:11434", "https://[::1]:11434"),
    ("http://localhost.evil:11434", None), ("http://localhost@evil", None),
    ("http://user@localhost", None), ("http://localhost:bad", None),
    ("http://localhost?upstream=evil", None), ("http://localhost/#fragment", None),
    ("http://localhost\n", None), ("file:///localhost", None),
])
def test_endpoint_is_literal_loopback_without_credentials_proxy_or_redirect_target(url, expected):
    assert local_narration_endpoint(url) == expected


@pytest.mark.parametrize("restart", [False, True])
def test_intent_is_approval_bound_never_latest_or_foreign_session(rig, restart):
    rig.service = rig.enable("JARVIS_TOOL_SUMMARY_VIA_LLM")
    rig.summary.side_effect = None
    rig.summary.return_value = "Safari ist geöffnet."

    async def scenario():
        approval_id = await request_approval(rig)
        await rig.db.add_message(session_id="session", role="user", content="UNRELATED_LATER_MESSAGE")
        await rig.db.create_session("other-session")
        await rig.db.add_message(session_id="other-session", role="user", content="FOREIGN_PRIVATE_MESSAGE")
        await rig.db.add_memory_item("other-session", "FOREIGN_PRIVATE_MEMORY", 1.0)
        if restart:
            rig.service = rig.enable("JARVIS_TOOL_SUMMARY_VIA_LLM")
        await rig.service.handle_approval_decision(approval_id, "approve")
        messages = rig.summary.call_args.kwargs["messages"]
        evidence = json.loads(messages[-1]["content"])
        assert evidence["user_intent"] == (None if restart else "oeffne Safari")
        assert len(messages) == 2
        assert "UNRELATED" not in str(messages) and "FOREIGN_PRIVATE" not in str(messages)
        assert not rig.service.turn_engine._narration_intents

    asyncio.run(scenario())


def test_pending_intent_cache_is_bounded_and_mismatched_ids_cannot_supply_context(rig, monkeypatch):
    from jarvis_agent.orchestration import turn_engine

    rig.service = rig.enable("JARVIS_TOOL_SUMMARY_VIA_LLM")
    monkeypatch.setattr(turn_engine, "MAX_PENDING_INTENTS", 2)
    rig.summary.side_effect = None
    rig.summary.return_value = "Safari ist geöffnet."
    rig.tools.execute.side_effect = None
    rig.tools.execute.return_value = ToolResult(True, "Erledigt")

    async def scenario():
        ids = []
        for i in range(3):
            await rig.service.start_run("session", f"run-{i}", "oeffne Safari")
            ids.append(rig.events[-1]["data"]["approval"]["id"])
        cache = rig.service.turn_engine._narration_intents
        assert list(cache) == ids[1:]
        cache[ids[2]] = ("foreign-session", "run-2", "FOREIGN_PRIVATE")
        await rig.service.handle_approval_decision(ids[2], "approve")
        assert json.loads(rig.summary.call_args.kwargs["messages"][-1]["content"])["user_intent"] is None
        await rig.service.handle_approval_decision(ids[1], "deny")
        assert not cache

    asyncio.run(scenario())


@pytest.mark.parametrize("name,args,command,output", [
    ("open_app", {"app_name": "safari"}, ["open", "-a", "Safari"], "App geoeffnet: Safari"),
    ("open_url", {"url": "https://example.org"}, ["open", "https://example.org"], "URL geoeffnet: https://example.org"),
])
def test_real_registry_and_tool_validation_precede_narration(rig, monkeypatch, name, args, command, output):
    from jarvis_agent.tools import ToolRegistry, system_tools

    calls = []

    async def run_command(argv):
        calls.append(argv)
        assert (await rig.db.get_approval("actual-tool-approval"))["status"] == "approved"
        assert tool_rows(rig) == []
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(system_tools, "run_command", run_command)
    rig.service = rig.enable("JARVIS_TOOL_SUMMARY_VIA_LLM")
    rig.service.turn_engine.tools = ToolRegistry()
    rig.summary.side_effect = None
    rig.summary.return_value = "Der Auftrag ist ausgeführt."

    async def scenario():
        await rig.db.create_approval("actual-tool-approval", "session", "run", name, args)
        await rig.service.handle_approval_decision("actual-tool-approval", "approve")
        assert calls == [command]
        assert tool_rows(rig)[0][-3:] == (1, output, None)
        evidence = json.loads(rig.summary.call_args.kwargs["messages"][-1]["content"])
        assert evidence["tool_output"] == output
        assert evidence["validated_tool_input"] == args
        rig.summary.assert_awaited_once()

    asyncio.run(scenario())


def test_default_on_does_not_add_any_model_call_to_normal_conversation(rig, monkeypatch):
    monkeypatch.delenv("JARVIS_TOOL_SUMMARY_VIA_LLM")
    rig.service = AgentService(rig.db, rig.service.turn_engine.responses.event_bus, rig.tools, rig.service.profile_path)
    rig.set_stream(["Hallo, schön dich zu sehen."])
    asyncio.run(rig.service.start_run("session", "chat-run", "Hallo Jarvis"))
    rig.stream.assert_called_once()
    rig.summary.assert_not_awaited()
    rig.planner.assert_not_awaited()
    rig.tools.execute.assert_not_awaited()
    assert rig.events[-2]["content"] == "Hallo, schön dich zu sehen."


@pytest.mark.parametrize("decision,success", [("deny", True), ("approve", False)])
def test_denied_or_failed_tool_never_enters_narration(rig, decision, success):
    rig.service = rig.enable("JARVIS_TOOL_SUMMARY_VIA_LLM")

    async def scenario():
        approval_id = await request_approval(rig)
        if not success:
            rig.tools.execute.side_effect = None
            rig.tools.execute.return_value = ToolResult(False, "", "permission denied")
        await rig.service.handle_approval_decision(approval_id, decision)
        rig.summary.assert_not_awaited()
        if decision == "deny":
            rig.tools.execute.assert_not_awaited()
            assert tool_rows(rig) == []
            assert "nichts ausgefuehrt" in rig.events[-2]["content"]
        else:
            rig.tools.execute.assert_awaited_once()
            assert tool_rows(rig)[0][-3:] == (0, "", "permission denied")
            assert rig.events[-1]["state"] == "error"
            assert "fehlgeschlagen" in rig.events[-2]["content"]

    asyncio.run(scenario())


def test_explicit_disable_keeps_legacy_technical_result(rig):
    async def scenario():
        approval_id = await request_approval(rig)
        await rig.service.handle_approval_decision(approval_id, "approve")
        rig.summary.assert_not_awaited()
        assert rig.events[-2]["content"] == "Aktion abgeschlossen (open_app). Ergebnis: Erledigt"
        assert len(tool_rows(rig)) == 1

    asyncio.run(scenario())


def test_result_persistence_failure_never_publishes_model_success(rig, monkeypatch):
    rig.service = rig.enable("JARVIS_TOOL_SUMMARY_VIA_LLM")

    async def fail(**kwargs):
        raise sqlite3.OperationalError("fixture: persistence unavailable")

    monkeypatch.setattr(rig.db, "add_tool_run", fail)

    async def scenario():
        approval_id = await request_approval(rig)
        with pytest.raises(sqlite3.OperationalError):
            await rig.service.handle_approval_decision(approval_id, "approve")
        rig.tools.execute.assert_awaited_once()
        rig.summary.assert_not_awaited()
        assert not any(event["event"] == "message" for event in rig.events)
        assert tool_rows(rig) == []

    asyncio.run(scenario())
