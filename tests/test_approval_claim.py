"""YJSEC-01: real SQLite claims; fixtures prove dispatch, not external OS effects."""

import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from jarvis_agent.agent_service import AgentService
from jarvis_agent.db import Database
from jarvis_agent.orchestration import legacy_responses as response_module
from jarvis_agent.tools import ToolRegistry
from jarvis_agent.tools.base import ToolResult


@pytest.fixture
def claims(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_TOOL_SUMMARY_VIA_LLM", "0")
    monkeypatch.setenv("JARVIS_ENABLE_TOOL_PLANNER", "0")
    events = []
    tools = ToolRegistry()
    tools.execute = AsyncMock(return_value=ToolResult(True, "App geoeffnet: Safari"))
    summary = AsyncMock(return_value='Der Öffnungsbefehl für die App "Safari" wurde erfolgreich ausgeführt.')
    monkeypatch.setattr(response_module, "complete_chat", summary)

    async def publish(session_id, payload):
        events.append((session_id, payload))

    def service():
        db = Database(tmp_path / "claims.db", tmp_path, tmp_path / "model.bin")
        return AgentService(db, SimpleNamespace(publish=publish), tools, tmp_path / "profile.json")

    owner = service()

    async def initialize():
        await owner.db.init()
        await owner.db.create_session("session")
        await owner.db.create_session("other-session")

    asyncio.run(initialize())
    return SimpleNamespace(owner=owner, service=service, events=events, tools=tools, summary=summary)


async def pending(claims, service=None, approval_id="approval", session_id="session", run_id="run"):
    service = service or claims.owner
    await service.db.upsert_learned_command(trigger="fokus", tool_name="open_app", tool_input={"app_name": "Safari"})
    service.learning.mark_pending_trigger(run_id, "fokus")
    service.turn_engine._narration_intents[approval_id] = (session_id, run_id, "fokus")
    return await service.db.create_approval(
        approval_id, session_id, run_id, "open_app", {"app_name": "Safari"},
    )


def rows(claims, table):
    assert table in {"tool_runs", "messages", "tool_learning_stats", "learned_commands", "approvals"}
    with sqlite3.connect(claims.owner.db.db_path) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]


def gate_pending_reads(monkeypatch, services):
    """Both tasks read the actual pending row before either may continue."""
    barrier = asyncio.Barrier(2)
    for db in {service.db for service in services}:
        original = db.get_approval

        async def read(approval_id, _original=original):
            approval = await _original(approval_id)
            assert approval["status"] == "pending"
            await barrier.wait()
            return approval

        monkeypatch.setattr(db, "get_approval", read)


@pytest.mark.parametrize("separate_services", [False, True])
@pytest.mark.parametrize("narration", [False, True])
@pytest.mark.parametrize("tool_success", [False, True])
@pytest.mark.parametrize("decisions", [("approve", "approve"), ("approve", "deny"), ("deny", "deny")])
def test_concurrent_decisions_have_one_winner(claims, monkeypatch, separate_services, narration, tool_success, decisions):
    async def scenario():
        first = claims.owner
        second = claims.service() if separate_services else first
        for service in (first, second):
            service.turn_engine.responses.enable_llm_tool_summary = narration
        if not tool_success:
            claims.tools.execute.return_value = ToolResult(False, "", "fixture tool failure")
        await pending(claims)
        if separate_services:
            second.learning.mark_pending_trigger("run", "fokus")
            second.turn_engine._narration_intents["approval"] = ("session", "run", "fokus")
        gate_pending_reads(monkeypatch, (first, second))
        results = await asyncio.wait_for(asyncio.gather(
            first.handle_approval_decision("approval", decisions[0]),
            second.handle_approval_decision("approval", decisions[1]),
            return_exceptions=True,
        ), timeout=10)
        winners = [i for i, result in enumerate(results) if isinstance(result, str)]
        assert len(winners) == 1, results
        winner = winners[0]
        loser = 1 - winner
        assert isinstance(results[loser], ValueError)
        assert str(results[loser]) == "Approval wurde bereits entschieden"
        approved = decisions[winner] == "approve"
        assert results[winner] == ("approved" if approved else "denied")
        approval = rows(claims, "approvals")[0]
        assert (approval["status"], approval["decision"]) == (results[winner], decisions[winner])
        assert approval["decided_at"]
        assert claims.tools.execute.await_count == int(approved)
        tool_runs = rows(claims, "tool_runs")
        assert len(tool_runs) == int(approved)
        if approved:
            assert (tool_runs[0]["session_id"], tool_runs[0]["run_id"]) == ("session", "run")
        stats = await first.db.get_tool_learning_stats()
        assert len(stats) == int(approved)
        if approved:
            assert (stats[0]["success_count"], stats[0]["failure_count"]) == (int(tool_success), int(not tool_success))
        learned = await first.db.get_learned_command("fokus")
        assert (learned["usage_count"], learned["success_count"], learned["failure_count"]) == (
            int(approved), int(approved and tool_success), int(approved and not tool_success),
        )
        assert len(rows(claims, "messages")) == 1
        assert [payload.get("state", payload["event"]) for _, payload in claims.events] == (
            ["executing", "message", "done" if tool_success else "error"] if approved else ["message", "done"]
        )
        assert all(session == "session" and payload["run_id"] == "run" for session, payload in claims.events)
        assert claims.summary.await_count == int(approved and tool_success and narration)
        if separate_services:
            losing_service = (first, second)[loser]
            assert losing_service.learning.pending_learned_trigger_by_run == {"run": "fokus"}
            assert "approval" in losing_service.turn_engine._narration_intents

    asyncio.run(scenario())


@pytest.mark.parametrize("winner_decision", ["approve", "deny"])
def test_loser_cannot_consume_winners_context_or_affect_other_runs(claims, monkeypatch, winner_decision):
    async def scenario():
        service = claims.owner
        await pending(claims)
        await service.db.create_approval("other-approval", "other-session", "other-run", "open_app", {"app_name": "Safari"})
        service.learning.mark_pending_trigger("other-run", "other-trigger")
        service.turn_engine._narration_intents["other-approval"] = ("other-session", "other-run", "other-intent")
        original = service.db.resolve_approval
        original_get = service.db.get_approval
        committed = asyncio.Event()
        loser_finished = asyncio.Event()

        async def resolve(**kwargs):
            if asyncio.current_task().get_name() == "winner":
                result = await original(**kwargs)
                assert result is True
                committed.set()
                await loser_finished.wait()
                # The loser returned after this commit, before the winner resumes.
                assert service.learning.pending_learned_trigger_by_run["run"] == "fokus"
                assert service.turn_engine._narration_intents["approval"] == ("session", "run", "fokus")
                assert claims.events == []
                assert rows(claims, "tool_runs") == rows(claims, "messages") == []
                return result
            await committed.wait()
            return await original(**kwargs)

        gate_pending_reads(monkeypatch, (service,))
        monkeypatch.setattr(service.db, "resolve_approval", resolve)
        winner = asyncio.create_task(service.handle_approval_decision("approval", winner_decision), name="winner")

        async def lose():
            try:
                with pytest.raises(ValueError, match="bereits entschieden"):
                    await service.handle_approval_decision("approval", "deny" if winner_decision == "approve" else "approve")
            finally:
                loser_finished.set()

        await asyncio.wait_for(asyncio.gather(winner, lose()), timeout=10)
        other = await original_get("other-approval")
        assert other["status"] == "pending" and other["decided_at"] is None
        assert service.learning.pending_learned_trigger_by_run == {"other-run": "other-trigger"}
        assert service.turn_engine._narration_intents == {
            "other-approval": ("other-session", "other-run", "other-intent"),
        }
        assert await service.db.list_messages("other-session") == []
        # An unrelated session can still execute its own approval normally.
        monkeypatch.setattr(service.db, "get_approval", original_get)
        monkeypatch.setattr(service.db, "resolve_approval", original)
        await service.handle_approval_decision("other-approval", "approve")
        assert len(await service.db.list_messages("other-session")) == 1
        assert rows(claims, "tool_runs")[-1]["run_id"] == "other-run"

    asyncio.run(scenario())


@pytest.mark.parametrize("decision", ["approve", "deny"])
def test_database_claim_is_committed_once_across_connections(claims, decision):
    async def scenario():
        await pending(claims)
        other = claims.service().db
        barrier = asyncio.Barrier(2)
        status = "approved" if decision == "approve" else "denied"

        async def claim(db):
            await barrier.wait()
            return await db.resolve_approval("approval", status, decision)

        results = await asyncio.wait_for(asyncio.gather(claim(claims.owner.db), claim(other)), timeout=10)
        assert sorted(results) == [False, True]
        saved = await other.get_approval("approval")
        assert saved["status"] == status and saved["decision"] == decision and saved["decided_at"]
        assert await other.resolve_approval("approval", "denied", "deny") is False
        assert await other.get_approval("approval") == saved
        assert await other.resolve_approval("missing", status, decision) is False

    asyncio.run(scenario())


@pytest.mark.parametrize("status,decision", [("pending", "approve"), ("approved", "deny"), ("denied", "approve"), ("approved", "invalid")])
def test_database_rejects_invalid_pairs_without_consuming_pending(claims, status, decision):
    async def scenario():
        await pending(claims)
        before = await claims.owner.db.get_approval("approval")
        with pytest.raises(ValueError, match="Ungueltige Entscheidung"):
            await claims.owner.db.resolve_approval("approval", status, decision)
        assert await claims.owner.db.get_approval("approval") == before

    asyncio.run(scenario())


@pytest.mark.parametrize("first_decision", ["approve", "deny"])
def test_sequential_replays_are_silent_and_cannot_overwrite_decision(claims, first_decision):
    async def scenario():
        await pending(claims)
        await claims.owner.handle_approval_decision("approval", first_decision)
        before = {table: rows(claims, table) for table in ("approvals", "tool_runs", "messages", "tool_learning_stats", "learned_commands")}
        events = list(claims.events)
        dispatches = claims.tools.execute.await_count
        for service in (claims.owner, claims.service()):
            for decision in ("approve", "deny", "invalid"):
                with pytest.raises(ValueError, match="bereits entschieden"):
                    await service.handle_approval_decision("approval", decision)
        assert before == {table: rows(claims, table) for table in before}
        assert claims.events == events
        assert claims.tools.execute.await_count == dispatches

    asyncio.run(scenario())


@pytest.mark.parametrize("approval_id,decision,message", [
    ("missing", "approve", "nicht gefunden"),
    ("missing", "deny", "nicht gefunden"),
    ("missing", "invalid", "nicht gefunden"),
    ("approval", "invalid", "Ungueltige Entscheidung"),
])
def test_invalid_or_unknown_request_preserves_all_pending_context(claims, approval_id, decision, message):
    async def scenario():
        await pending(claims)
        service = claims.owner
        before = await service.db.get_approval("approval")
        with pytest.raises(ValueError, match=message):
            await service.handle_approval_decision(approval_id, decision)
        assert await service.db.get_approval("approval") == before
        assert service.learning.pending_learned_trigger_by_run == {"run": "fokus"}
        assert "approval" in service.turn_engine._narration_intents
        assert claims.events == []
        assert rows(claims, "tool_runs") == rows(claims, "messages") == []
        claims.tools.execute.assert_not_awaited()
        claims.summary.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize("phase", ["claim_write", "claim_commit", "tool_result", "learning", "assistant_message"])
def test_persistence_failures_do_not_publish_success_or_allow_replay(claims, monkeypatch, phase):
    async def scenario():
        service = claims.owner
        await pending(claims)
        service.turn_engine.responses.enable_llm_tool_summary = True

        async def fail(*args, **kwargs):
            raise sqlite3.OperationalError("fixture persistence failure")

        with monkeypatch.context() as patch:
            if phase == "claim_write":
                with sqlite3.connect(service.db.db_path) as connection:
                    connection.execute("""CREATE TRIGGER reject_claim BEFORE UPDATE ON approvals
                                          BEGIN SELECT RAISE(ABORT, 'fixture persistence failure'); END""")
            elif phase == "claim_commit":
                import aiosqlite
                patch.setattr(aiosqlite.Connection, "commit", fail)
            else:
                method = {"tool_result": "add_tool_run", "learning": "record_tool_learning", "assistant_message": "add_message"}[phase]
                patch.setattr(service.db, method, fail)
            with pytest.raises(sqlite3.DatabaseError, match="fixture persistence failure"):
                await service.handle_approval_decision("approval", "approve")

        preclaim = phase in {"claim_write", "claim_commit"}
        assert (await service.db.get_approval("approval"))["status"] == ("pending" if preclaim else "approved")
        assert claims.tools.execute.await_count == int(not preclaim)
        assert len(rows(claims, "tool_runs")) == int(phase in {"learning", "assistant_message"})
        assert rows(claims, "messages") == []
        assert not any(payload["event"] == "message" or payload.get("state") == "done" for _, payload in claims.events)
        assert claims.summary.await_count == int(phase == "assistant_message")
        if preclaim:
            assert service.learning.pending_learned_trigger_by_run == {"run": "fokus"}
            assert "approval" in service.turn_engine._narration_intents
        else:
            with pytest.raises(ValueError, match="bereits entschieden"):
                await claims.service().handle_approval_decision("approval", "approve")
            claims.tools.execute.assert_awaited_once()

    asyncio.run(scenario())


@pytest.mark.parametrize("boundary", ["before_claim", "after_claim", "during_dispatch", "before_result", "before_narration"])
def test_cancellation_and_restart_never_replay_a_committed_claim(claims, monkeypatch, boundary):
    """Cancel at real lifecycle boundaries, then reconstruct services on the same file.

    This simulates durable restart states; it does not prove an OS action or a
    real process kill. Even an unobserved dispatch is never retried after claim.
    """
    async def scenario():
        service = claims.owner
        await pending(claims)
        entered = asyncio.Event()
        hold = asyncio.Event()

        async def stop_here():
            entered.set()
            await hold.wait()

        with monkeypatch.context() as patch:
            if boundary in {"before_claim", "after_claim"}:
                original = service.db.resolve_approval

                async def resolve(**kwargs):
                    if boundary == "before_claim":
                        await stop_here()
                    result = await original(**kwargs)
                    if boundary == "after_claim":
                        await stop_here()
                    return result

                patch.setattr(service.db, "resolve_approval", resolve)
            elif boundary == "during_dispatch":
                async def dispatch(**kwargs):
                    await stop_here()

                claims.tools.execute.side_effect = dispatch
            elif boundary == "before_result":
                patch.setattr(service.db, "add_tool_run", lambda **kwargs: stop_here())
            else:
                patch.setattr(service.turn_engine.responses, "compose_tool_response", lambda **kwargs: stop_here())

            task = asyncio.create_task(service.handle_approval_decision("approval", "approve"))
            await asyncio.wait_for(entered.wait(), timeout=10)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        dispatched = boundary in {"during_dispatch", "before_result", "before_narration"}
        assert claims.tools.execute.await_count == int(dispatched)
        assert len(rows(claims, "tool_runs")) == int(boundary == "before_narration")
        assert rows(claims, "messages") == []
        assert not any(payload["event"] == "message" or payload.get("state") == "done" for _, payload in claims.events)
        restarted = claims.service()
        await restarted.db.init()
        assert restarted.learning.pending_learned_trigger_by_run == {}
        assert restarted.turn_engine._narration_intents == {}
        if boundary == "before_claim":
            assert (await restarted.db.get_approval("approval"))["status"] == "pending"
            await restarted.handle_approval_decision("approval", "approve")
            claims.tools.execute.assert_awaited_once()
        else:
            assert (await restarted.db.get_approval("approval"))["status"] == "approved"
            for decision in ("approve", "deny"):
                with pytest.raises(ValueError, match="bereits entschieden"):
                    await restarted.handle_approval_decision("approval", decision)
            assert claims.tools.execute.await_count == int(dispatched)

    asyncio.run(scenario())
