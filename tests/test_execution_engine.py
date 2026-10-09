import asyncio

from jarvis_agent.execution_engine import StepExecutor
from jarvis_agent.tools.base import ToolResult


def test_step_executor_emits_consistent_steps_without_recovery():
    async def _run() -> None:
        executor = StepExecutor()
        seen_details: list[str] = []

        async def emit_state(_session_id: str, _run_id: str, detail: str, _data):
            seen_details.append(detail)

        async def execute_tool() -> ToolResult:
            return ToolResult(success=True, output="ok")

        outcome = await executor.run_tool_flow(
            session_id="session",
            run_id="run",
            tool_name="open_app",
            tool_input={"app_name": "Notes"},
            emit_state=emit_state,
            execute_tool=execute_tool,
        )

        assert outcome.tool_result.success is True
        assert outcome.used_recovery is False
        assert "Step 1/4 plan: open_app" in seen_details
        assert "Step 2/4 validate: open_app" in seen_details
        assert "Step 3/4 execute: open_app" in seen_details
        assert any(item.startswith("Step 4/4 verify:") for item in seen_details)

    asyncio.run(_run())


def test_step_executor_emits_recovery_step_with_total_five():
    async def _run() -> None:
        executor = StepExecutor()
        seen_details: list[str] = []

        async def emit_state(_session_id: str, _run_id: str, detail: str, _data):
            seen_details.append(detail)

        async def execute_tool() -> ToolResult:
            return ToolResult(success=False, output="", error="failed")

        async def recovery() -> ToolResult:
            return ToolResult(success=True, output="fallback-ok")

        outcome = await executor.run_tool_flow(
            session_id="session",
            run_id="run",
            tool_name="open_app",
            tool_input={"app_name": "Notes"},
            emit_state=emit_state,
            execute_tool=execute_tool,
            recovery=recovery,
        )

        assert outcome.tool_result.success is True
        assert outcome.used_recovery is True
        assert "Step 1/5 plan: open_app" in seen_details
        assert "Step 2/5 validate: open_app" in seen_details
        assert "Step 3/5 execute: open_app" in seen_details
        assert any(item.startswith("Step 4/5 verify:") for item in seen_details)
        assert "Step 5/5 recovery: starte fallback" in seen_details

    asyncio.run(_run())
