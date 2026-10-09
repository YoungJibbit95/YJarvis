"""Opt-in, single-decision semantic fallback for already unambiguous safety gates."""
from __future__ import annotations

import asyncio
from typing import Any

from ..learning_engine import LearningEngine
from ..llm import plan_tool_call
from ..tools import ToolRegistry
from . import semantic_pilot
from .semantic_pilot import SemanticDecision

SEMANTIC_TIMEOUT_SECONDS = 9.0


class LegacyPlannerAdapter:
    def __init__(
        self,
        tools: ToolRegistry,
        learning: LearningEngine,
        *,
        enable_tool_planner: bool,
    ) -> None:
        self.tools = tools
        self.learning = learning
        # Reuse the existing default-OFF explicit developer flag.
        self.enable_tool_planner = enable_tool_planner

    async def plan(self, user_message: str, settings: dict[str, Any]) -> SemanticDecision | None:
        if not self.enable_tool_planner:
            return None
        if not semantic_pilot.eligible_for_pilot(user_message):
            return None
        if not semantic_pilot.supported_legacy_platform():
            # Every currently allowlisted legacy implementation is macOS-only.
            return None

        allowed = [
            spec for spec in self.tools.list_specs()
            if spec["tool_name"] in semantic_pilot.PILOT_TOOL_NAMES
            and spec.get("requires_approval") is True
        ]
        if not allowed:
            return None
        try:
            ranked = await self.learning.rank_tool_specs_for_planner(allowed)
            proposed = await asyncio.wait_for(
                plan_tool_call(
                    base_url=str(settings.get("ollama_base_url", "http://127.0.0.1:11434")),
                    model=str(settings.get("model_name", "qwen2.5:3b-instruct")),
                    user_message=user_message,
                    tool_specs=ranked,
                ),
                timeout=SEMANTIC_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            # Any parser/model failure is a rejection, not a reason to execute.
            return None

        try:
            return semantic_pilot.validate_semantic_decision(
                proposed, user_message, {spec["tool_name"] for spec in allowed},
            )
        except Exception:
            return None
