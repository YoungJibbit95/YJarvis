"""Existing single-tool planner fallback; no lifecycle, execution or V2 plans."""

from __future__ import annotations

from typing import Any

from ..conversation_helpers import looks_like_tool_request
from ..learning_engine import LearningEngine
from ..llm import plan_tool_call
from ..tool_intent import ToolCallIntent
from ..tools import ToolRegistry


class LegacyPlannerAdapter:
    def __init__(
        self, tools: ToolRegistry, learning: LearningEngine, *, enable_tool_planner: bool,
    ) -> None:
        self.tools = tools
        self.learning = learning
        self.enable_tool_planner = enable_tool_planner

    async def plan(self, user_message: str, settings: dict[str, Any]) -> ToolCallIntent | None:
        if not self.enable_tool_planner:
            return None

        if not looks_like_tool_request(user_message):
            return None

        ranked_tool_specs = await self.learning.rank_tool_specs_for_planner(self.tools.list_specs())
        try:
            planned = await plan_tool_call(
                base_url=str(settings.get("ollama_base_url", "http://127.0.0.1:11434")),
                model=str(settings.get("model_name", "qwen2.5:3b-instruct")),
                user_message=user_message,
                tool_specs=ranked_tool_specs,
            )
        except Exception:
            return None

        if not planned:
            return None

        tool_name = str(planned.get("tool_name", "")).strip()
        tool_input = planned.get("tool_input")
        reason = str(planned.get("reason", "LLM Planner"))

        if not tool_name or not isinstance(tool_input, dict):
            return None

        if not self.tools.has_tool(tool_name):
            return None

        intent = ToolCallIntent(
            tool_name=tool_name,
            tool_input=tool_input,
            reason=reason,
        )
        return await self.learning.apply_adaptive_routing(intent)
