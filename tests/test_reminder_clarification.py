"""Reminder follow-up never creates OS state without the existing approval."""
import asyncio

import pytest

from jarvis_agent.orchestration.reminder_clarification import ReminderClarifications
from test_turn_lifecycle import rig, event_order


def test_time_missing_then_single_explicit_date_time_requires_approval(rig):
    async def scenario():
        await rig.service.start_run("session", "first", "Erinnere mich an den Einkauf.")
        assert rig.events[-2]["content"] == "Wann soll ich dich daran erinnern?"
        pending = rig.service.turn_engine.routing.reminder_clarifications
        assert pending.has_pending("session")
        await rig.service.start_run("session", "second", "Morgen um 10 Uhr.")
        approval = (await rig.db.list_pending_approvals())[0]
        assert approval["tool_name"] == "reminder_create"
        assert approval["tool_input"]["title"] == "Einkauf"
        assert approval["tool_input"]["due_at"].endswith("T10:00")
        assert rig.events[-1]["state"] == "approval_required"
        assert not pending.has_pending("session")
        rig.tools.execute.assert_not_awaited()
        rig.planner.assert_not_awaited()
    asyncio.run(scenario())


def test_content_missing_then_title_requires_approval(rig):
    async def scenario():
        await rig.service.start_run("session", "first", "Mach mir morgen um 10 Uhr eine Erinnerung.")
        assert rig.events[-2]["content"] == "Woran soll ich dich erinnern?"
        await rig.service.start_run("session", "second", "An den Einkauf.")
        approval = (await rig.db.list_pending_approvals())[0]
        assert approval["tool_name"] == "reminder_create"
        assert approval["tool_input"]["title"] == "Einkauf"
        assert approval["tool_input"]["due_at"].endswith("T10:00")
        rig.tools.execute.assert_not_awaited()
    asyncio.run(scenario())


def test_ambiguous_answer_reasks_and_keeps_one_pending(rig):
    async def scenario():
        await rig.service.start_run("session", "first", "Erinnere mich an den Einkauf.")
        await rig.service.start_run("session", "ambiguous", "Irgendwann morgen früh.")
        assert "Datum und Uhrzeit eindeutig" in rig.events[-2]["content"]
        store = rig.service.turn_engine.routing.reminder_clarifications
        assert len(store.pending) == 1
        assert await rig.db.list_pending_approvals() == []
        await rig.service.start_run("session", "correct", "Morgen um 10 Uhr.")
        assert len(await rig.db.list_pending_approvals()) == 1
        rig.tools.execute.assert_not_awaited()
    asyncio.run(scenario())


def test_topic_change_cancels_pending_without_false_tool_action(rig):
    rig.set_stream(["Python ist eine Programmiersprache."])
    async def scenario():
        await rig.service.start_run("session", "first", "Erinnere mich an den Einkauf.")
        rig.events.clear()
        await rig.service.start_run("session", "second", "Ach egal, erklär mir lieber Python.")
        assert event_order(rig) == ["received", "thinking", "token", "message", "done"]
        assert await rig.db.list_pending_approvals() == []
        assert not rig.service.turn_engine.routing.reminder_clarifications.has_pending("session")
        rig.tools.execute.assert_not_awaited()
    asyncio.run(scenario())


def test_explicit_cancel_does_not_create_reminder(rig):
    async def scenario():
        await rig.service.start_run("session", "first", "Erinnere mich an den Einkauf.")
        await rig.service.start_run("session", "cancel", "Abbrechen")
        assert rig.events[-2]["content"] == "Okay, ich habe keine Erinnerung angelegt."
        assert await rig.db.list_pending_approvals() == []
        assert not rig.service.turn_engine.routing.reminder_clarifications.has_pending("session")
        rig.tools.execute.assert_not_awaited()
    asyncio.run(scenario())


def test_new_tool_request_discards_stale_pending(rig):
    async def scenario():
        await rig.service.start_run("session", "first", "Erinnere mich an den Einkauf.")
        await rig.service.start_run("session", "second", "Öffne Safari")
        approvals = await rig.db.list_pending_approvals()
        assert len(approvals) == 1 and approvals[0]["tool_name"] == "open_app"
        assert not rig.service.turn_engine.routing.reminder_clarifications.has_pending("session")
        rig.tools.execute.assert_not_awaited()
    asyncio.run(scenario())


def test_learned_command_is_not_mistaken_for_missing_reminder_title(rig):
    async def scenario():
        await rig.db.upsert_learned_command(
            trigger="fokus", tool_name="open_app", tool_input={"app_name": "Safari"},
        )
        await rig.service.start_run("session", "first", "Mach mir morgen um 10 Uhr eine Erinnerung.")
        await rig.service.start_run("session", "learned", "fokus")
        approvals = await rig.db.list_pending_approvals()
        assert len(approvals) == 1 and approvals[0]["tool_name"] == "open_app"
        assert not rig.service.turn_engine.routing.reminder_clarifications.has_pending("session")
        rig.tools.execute.assert_not_awaited()
    asyncio.run(scenario())


def test_full_assembled_text_is_checked_against_hard_safety(rig):
    rig.service.turn_engine._load_profile = lambda: {
        "safety": {"blocked_request_patterns": ["Erinnere mich am"]},
    }

    async def scenario():
        await rig.service.start_run("session", "first", "Erinnere mich an den Einkauf.")
        await rig.service.start_run("session", "second", "Morgen um 10 Uhr.")
        assert rig.events[-1]["detail"] == "Sicherheitsregel hat Anfrage blockiert"
        assert await rig.db.list_pending_approvals() == []
        rig.tools.execute.assert_not_awaited()
    asyncio.run(scenario())


def test_explicit_approval_is_still_required_before_any_execution(rig):
    async def scenario():
        await rig.service.start_run("session", "first", "Erinnere mich an den Einkauf.")
        await rig.service.start_run("session", "second", "Morgen um 10 Uhr.")
        approval = (await rig.db.list_pending_approvals())[0]
        rig.tools.execute.assert_not_awaited()
        assert await rig.service.handle_approval_decision(approval["id"], "deny") == "denied"
        rig.tools.execute.assert_not_awaited()
        assert (await rig.db.get_approval(approval["id"]))["status"] == "denied"
    asyncio.run(scenario())


def test_pending_is_strictly_scoped_and_expires_without_persistence():
    clock = [1.0]
    store = ReminderClarifications(clock=lambda: clock[0], ttl_seconds=5, max_sessions=2)
    assert store.begin("A", "Erinnere mich an den Einkauf.", "Wann soll ich dich daran erinnern?")
    assert store.consume("B", "Morgen um 10 Uhr.") is None
    assert store.has_pending("A")
    clock[0] = 6.0
    assert not store.has_pending("A")
    assert store.consume("A", "Morgen um 10 Uhr.") is None
    assert ReminderClarifications().pending == {}


def test_pending_is_bounded_to_one_per_session_and_total_sessions():
    store = ReminderClarifications(clock=lambda: 1.0, max_sessions=2)
    for session in ("A", "B", "C"):
        assert store.begin(session, "Erinnere mich an den Einkauf.", "Wann soll ich dich daran erinnern?")
    assert len(store.pending) == 2
    assert not store.has_pending("A")
    assert store.begin("B", "Erinnere mich an die Blumen.", "Wann soll ich dich daran erinnern?")
    assert len(store.pending) == 2
    assert store.pending["B"].title == "Blumen"


def test_missing_day_or_invalid_clock_never_sets_reminder(rig):
    async def scenario():
        await rig.service.start_run("session", "first", "Erinnere mich an den Einkauf.")
        for index, answer in enumerate(("10 Uhr", "Morgen um 28 Uhr", "Heute irgendwann")):
            await rig.service.start_run("session", f"invalid-{index}", answer)
            assert "Datum und Uhrzeit eindeutig" in rig.events[-2]["content"]
        assert await rig.db.list_pending_approvals() == []
        rig.tools.execute.assert_not_awaited()
    asyncio.run(scenario())


def test_small_talk_switch_is_not_swallowed_as_reminder_content(rig):
    rig.set_stream(["Sehr gerne."])

    async def scenario():
        await rig.service.start_run("session", "first", "Mach mir morgen um 10 Uhr eine Erinnerung.")
        await rig.service.start_run("session", "thanks", "Danke, Jarvis")
        assert rig.events[-2]["content"] == "Sehr gerne."
        assert await rig.db.list_pending_approvals() == []
        assert not rig.service.turn_engine.routing.reminder_clarifications.has_pending("session")
        rig.tools.execute.assert_not_awaited()
    asyncio.run(scenario())
