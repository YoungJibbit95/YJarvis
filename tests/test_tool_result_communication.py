"""YJCORE-01: characterize the real approval, SQLite and response boundary."""

import asyncio
import json
import sqlite3

import pytest

from jarvis_agent.tools.base import ToolResult
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
