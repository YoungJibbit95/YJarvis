"""Characterize the existing planner boundary before and after extraction."""

import asyncio
import ast
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from jarvis_agent.orchestration import legacy_planner as planner_module
from jarvis_agent.orchestration import legacy_routing, routing_stages
from jarvis_agent.tool_intent import ToolCallIntent
from jarvis_agent.tools import ToolRegistry
from test_turn_lifecycle import rig  # Reuse the real SQLite/lifecycle fixture.


@pytest.fixture
def planner(monkeypatch):
    tools = ToolRegistry()
    tools.execute = AsyncMock(side_effect=AssertionError("Planner must not execute"))
    specs = tools.list_specs()
    ranked = list(reversed(specs))
    learning = SimpleNamespace(
        rank_tool_specs_for_planner=AsyncMock(return_value=ranked),
        apply_adaptive_routing=AsyncMock(side_effect=lambda intent: intent),
    )
    call = AsyncMock(return_value={"tool_name": "open_app", "tool_input": {"app_name": "Safari"}})
    monkeypatch.setattr(planner_module, "plan_tool_call", call)
    adapter = planner_module.LegacyPlannerAdapter(tools, learning, enable_tool_planner=True)
    return SimpleNamespace(plan=adapter.plan, adapter=adapter, tools=tools,
                           learning=learning, call=call, specs=specs, ranked=ranked)


@pytest.mark.parametrize("enabled, message", [(False, "mach xyz"), (True, "Erzaehle etwas ueber Sterne")])
def test_gating_skips_ranking_model_and_adaptation(planner, enabled, message):
    planner.adapter.enable_tool_planner = enabled
    assert asyncio.run(planner.plan(message, {})) is None
    planner.learning.rank_tool_specs_for_planner.assert_not_awaited()
    planner.call.assert_not_awaited()
    planner.learning.apply_adaptive_routing.assert_not_awaited()
    planner.tools.execute.assert_not_awaited()


@pytest.mark.parametrize("output, expected", [
    (None, None),
    ({}, None),
    ({"tool_input": {}}, None),
    ({"tool_name": "   ", "tool_input": {}}, None),
    ({"tool_name": "open_app"}, None),
    ({"tool_name": "open_app", "tool_input": "invalid"}, None),
    ({"tool_name": "unknown", "tool_input": {}}, None),
    (RuntimeError("offline"), None),
    ({"tool_name": " open_app ", "tool_input": {"app_name": "Safari"}, "reason": "planner"},
     ToolCallIntent("open_app", {"app_name": "Safari"}, "planner")),
    ({"tool_name": "open_app", "tool_input": {}}, ToolCallIntent("open_app", {}, "LLM Planner")),
])
def test_result_validation_and_model_exception_fallback(planner, output, expected):
    if isinstance(output, Exception):
        planner.call.side_effect = output
    else:
        planner.call.return_value = output
    assert asyncio.run(planner.plan("mach xyz", {})) == expected
    planner.learning.rank_tool_specs_for_planner.assert_awaited_once_with(planner.specs)
    planner.call.assert_awaited_once_with(
        base_url="http://127.0.0.1:11434", model="qwen2.5:3b-instruct",
        user_message="mach xyz", tool_specs=planner.ranked,
    )
    if expected is None:
        planner.learning.apply_adaptive_routing.assert_not_awaited()
    else:
        planner.learning.apply_adaptive_routing.assert_awaited_once_with(expected)
    planner.tools.execute.assert_not_awaited()


def test_settings_and_ranked_specs_reach_same_model_call(planner):
    asyncio.run(planner.plan("mach xyz", {"ollama_base_url": "http://model:1234", "model_name": "custom"}))
    planner.call.assert_awaited_once_with(
        base_url="http://model:1234", model="custom", user_message="mach xyz", tool_specs=planner.ranked,
    )


@pytest.mark.parametrize("failure_stage", ["ranking", "adaptation"])
def test_exception_boundary_is_not_broadened(planner, failure_stage):
    target = (planner.learning.rank_tool_specs_for_planner if failure_stage == "ranking"
              else planner.learning.apply_adaptive_routing)
    target.side_effect = RuntimeError(failure_stage)
    with pytest.raises(RuntimeError, match=failure_stage):
        asyncio.run(planner.plan("mach xyz", {}))
    assert planner.call.await_count == int(failure_stage == "adaptation")
    planner.tools.execute.assert_not_awaited()


def test_model_cancellation_propagates(planner):
    planner.call.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(planner.plan("mach xyz", {}))
    planner.learning.apply_adaptive_routing.assert_not_awaited()


@pytest.mark.parametrize("learned", [False, True])
def test_deterministic_intent_wins_before_model_call(rig, learned, monkeypatch):
    rig.service = rig.enable("JARVIS_ENABLE_TOOL_PLANNER")
    adapter = rig.service.turn_engine.routing.planner
    plan = AsyncMock(wraps=adapter.plan)
    monkeypatch.setattr(adapter, "plan", plan)

    async def check():
        if learned:
            await rig.db.upsert_learned_command(
                trigger="oeffne Safari", tool_name="open_app", tool_input={"app_name": "Notes"},
            )
        await rig.service.start_run("session", "run", "oeffne Safari")
        approval = (await rig.db.list_pending_approvals())[0]
        assert approval["tool_name"] == "open_app"
        assert approval["tool_input"] == {"app_name": "Notes" if learned else "Safari"}
        rig.planner.assert_not_awaited()
        plan.assert_not_awaited()
        rig.tools.execute.assert_not_awaited()
    asyncio.run(check())


def test_unset_runtime_flag_keeps_planner_off(rig, monkeypatch):
    from jarvis_agent.agent_service import AgentService

    monkeypatch.delenv("JARVIS_ENABLE_TOOL_PLANNER")
    service = AgentService(rig.db, rig.service.event_bus, rig.tools, rig.service.profile_path)
    asyncio.run(service.start_run("session", "run", "mach xyz"))
    rig.planner.assert_not_awaited()
    assert rig.events[-1]["detail"] == "Tool-Aufruf unklar, keine Ausfuehrung"


def test_planned_intent_uses_real_adaptation_then_requires_approval(rig):
    rig.service = rig.enable("JARVIS_ENABLE_TOOL_PLANNER")
    rig.planner.side_effect = None
    rig.planner.return_value = {"tool_name": "open_app", "tool_input": {"app_name": "Raycast"}, "reason": "planner"}

    async def check():
        for _ in range(3):
            await rig.db.record_tool_learning(tool_name="raycast_open", success=True, latency_ms=10)
        await rig.service.start_run("session", "run", "mach xyz")
        approval = (await rig.db.list_pending_approvals())[0]
        assert (approval["tool_name"], approval["tool_input"]) == ("raycast_open", {"fallback_text": ""})
        assert rig.events[-1]["state"] == "approval_required"
        assert rig.events[-1]["data"]["reason"] == "planner + adaptives Lernrouting"
        rig.planner.assert_awaited_once()
        rig.tools.execute.assert_not_awaited()
    asyncio.run(check())


@pytest.mark.parametrize("enabled", [False, True])
def test_learn_planner_resolution_does_not_recurse_or_replan_trigger(rig, enabled, monkeypatch):
    if enabled:
        rig.service = rig.enable("JARVIS_ENABLE_TOOL_PLANNER")
    rig.planner.side_effect = None
    rig.planner.return_value = {"tool_name": "open_app", "tool_input": {"app_name": "Safari"}}

    async def check():
        await rig.db.upsert_learned_command(
            trigger="mach xyz", tool_name="open_app", tool_input={"app_name": "Notes"},
        )
        resolver = AsyncMock(wraps=rig.service.learning.resolve_learned_command_intent)
        monkeypatch.setattr(rig.service.learning, "resolve_learned_command_intent", resolver)
        await rig.service.start_run("session", "learn", '/learn "fokus" => mach xyz')
        resolver.assert_not_awaited()
        stored = await rig.db.get_learned_command("fokus")
        assert rig.planner.await_count == int(enabled)
        assert await rig.db.list_pending_approvals() == []
        if enabled:
            assert (stored["tool_name"], stored["tool_input"]) == ("open_app", {"app_name": "Safari"})
            assert rig.planner.call_args.kwargs["user_message"] == "mach xyz"
            await rig.service.start_run("session", "execute", "fokus")
            approval = (await rig.db.list_pending_approvals())[0]
            assert (approval["tool_name"], approval["tool_input"]) == ("open_app", {"app_name": "Safari"})
            assert rig.planner.await_count == 1
            resolver.assert_awaited_once_with("fokus")
        else:
            assert stored is None
        rig.tools.execute.assert_not_awaited()
    asyncio.run(check())


@pytest.mark.parametrize("module", [legacy_routing, routing_stages, planner_module])
def test_planner_boundary_has_no_lifecycle_execution_or_os_responsibility(module):
    tree = ast.parse(inspect.getsource(module))
    imported = {part for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                for part in (node.module or "").split(".")}
    imported |= {part for node in ast.walk(tree) if isinstance(node, ast.Import)
                 for alias in node.names for part in alias.name.split(".")}
    assert not imported & {"os", "sys", "subprocess", "platform"}
    if module is not planner_module:
        assert "llm" not in imported
        assert not any(isinstance(node, ast.Name) and node.id == "plan_tool_call" for node in ast.walk(tree))
    else:
        assert not imported & {"events", "legacy_responses", "turn_engine", "domain"}
        assert not any(isinstance(node, ast.Attribute) and node.attr in
                       {"emit_state", "publish", "execute", "create_approval", "stream_response"}
                       for node in ast.walk(tree))
