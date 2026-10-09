from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from .tools.base import ToolResult


EmitStateFn = Callable[[str, str, str, dict[str, object] | None], Awaitable[None]]
ExecuteToolFn = Callable[[], Awaitable[ToolResult]]
RecoveryFn = Callable[[], Awaitable[ToolResult | None]]


@dataclass
class StepExecutionOutcome:
    tool_result: ToolResult
    latency_ms: int
    verified: bool
    used_recovery: bool


class StepExecutor:
    async def _emit_step(
        self,
        *,
        emit_state: EmitStateFn,
        session_id: str,
        run_id: str,
        detail: str,
        step_name: str,
        step_index: int,
        step_total: int,
        extra_data: dict[str, object] | None = None,
    ) -> None:
        payload = {"step": step_name, "step_index": step_index, "step_total": step_total}
        if extra_data:
            payload.update(extra_data)
        await emit_state(session_id, run_id, detail, payload)

    async def run_tool_flow(
        self,
        *,
        session_id: str,
        run_id: str,
        tool_name: str,
        tool_input: dict[str, object],
        emit_state: EmitStateFn,
        execute_tool: ExecuteToolFn,
        recovery: RecoveryFn | None = None,
    ) -> StepExecutionOutcome:
        step_total = 4 if recovery is None else 5
        await self._emit_step(
            emit_state=emit_state,
            session_id=session_id,
            run_id=run_id,
            detail=f"Step 1/{step_total} plan: {tool_name}",
            step_name="plan",
            step_index=1,
            step_total=step_total,
            extra_data={"tool_name": tool_name},
        )

        await self._emit_step(
            emit_state=emit_state,
            session_id=session_id,
            run_id=run_id,
            detail=f"Step 2/{step_total} validate: {tool_name}",
            step_name="validate",
            step_index=2,
            step_total=step_total,
        )
        if not tool_name:
            result = ToolResult(success=False, output="", error="tool_name fehlt")
            return StepExecutionOutcome(tool_result=result, latency_ms=0, verified=False, used_recovery=False)

        await self._emit_step(
            emit_state=emit_state,
            session_id=session_id,
            run_id=run_id,
            detail=f"Step 3/{step_total} execute: {tool_name}",
            step_name="execute",
            step_index=3,
            step_total=step_total,
        )
        started_at = time.perf_counter()
        result = await execute_tool()
        latency_ms = max(0, int(round((time.perf_counter() - started_at) * 1000)))

        verified = bool(result.success)
        await self._emit_step(
            emit_state=emit_state,
            session_id=session_id,
            run_id=run_id,
            detail=f"Step 4/{step_total} verify: {'ok' if verified else 'failed'}",
            step_name="verify",
            step_index=4,
            step_total=step_total,
            extra_data={"verified": verified, "latency_ms": latency_ms},
        )
        if verified or recovery is None:
            return StepExecutionOutcome(
                tool_result=result,
                latency_ms=latency_ms,
                verified=verified,
                used_recovery=False,
            )

        await self._emit_step(
            emit_state=emit_state,
            session_id=session_id,
            run_id=run_id,
            detail=f"Step 5/{step_total} recovery: starte fallback",
            step_name="recovery",
            step_index=5,
            step_total=step_total,
        )
        recovery_result = await recovery()
        if recovery_result is None:
            return StepExecutionOutcome(
                tool_result=result,
                latency_ms=latency_ms,
                verified=False,
                used_recovery=False,
            )
        return StepExecutionOutcome(
            tool_result=recovery_result,
            latency_ms=latency_ms,
            verified=bool(recovery_result.success),
            used_recovery=True,
        )
