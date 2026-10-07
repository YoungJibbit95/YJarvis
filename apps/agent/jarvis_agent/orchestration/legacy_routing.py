"""Order legacy stages, translate confirmation metadata and retain planner fallback."""

from __future__ import annotations

from typing import Any

from ..conversation_helpers import looks_like_tool_request, normalize_honorifics
from ..learning_engine import LearningEngine
from ..llm import plan_tool_call
from ..tool_intent import ToolCallIntent
from ..tools import ToolRegistry
from .legacy_responses import LegacyResponses
from .routing_stages import (
    LegacyHeuristicFastPath,
    LegacyLearningStage,
    LegacyRoute,
    LegacySafetyStage,
    LocalFastPaths,
)


class LegacyRouting:
    def __init__(
        self,
        tools: ToolRegistry,
        learning: LearningEngine,
        responses: LegacyResponses,
        *,
        enable_tool_planner: bool,
    ) -> None:
        self.tools = tools
        self.learning = learning
        self.responses = responses
        self.enable_tool_planner = enable_tool_planner
        self.safety = LegacySafetyStage()
        self.learning_stage = LegacyLearningStage(learning)
        self.local = LocalFastPaths()
        self.heuristic = LegacyHeuristicFastPath(tools)
        self.pending_confirmations = self.safety.pending_confirmations

    async def route(
        self,
        session_id: str,
        run_id: str,
        user_message: str,
        profile: dict[str, Any],
        settings: dict[str, Any],
    ) -> LegacyRoute:
        confirmation = self.safety.resolve_confirmation(session_id, user_message, profile)
        normalized_user_message = confirmation.user_message
        if confirmation.was_policy_confirmed:
            # Keep wire timing even if a later stage blocks or raises. Only this
            # compatibility layer translates the decision into a lifecycle event.
            await self.responses.emit_state(
                session_id=session_id,
                run_id=run_id,
                state="thinking",
                detail="Sicherheitsbestaetigung akzeptiert",
            )

        safety_route = self.safety.check(session_id, confirmation, profile)
        if safety_route is not None:
            return safety_route

        learning_route = await self.learning_stage.instruction(
            normalized_user_message, settings, self._decide_tool_intent,
        )
        if learning_route is not None:
            return learning_route

        local_route = self.local.route(normalized_user_message, settings)
        if local_route is not None:
            return local_route

        intent = await self._decide_tool_intent(normalized_user_message, settings)
        if intent is None and looks_like_tool_request(normalized_user_message):
            return LegacyRoute(
                normalized_user_message,
                reply=normalize_honorifics(
                    "Ich habe den Tool-Aufruf nicht eindeutig erkannt und fuehre daher nichts blind aus. "
                    "Formulieren Sie bitte konkret, z. B. `Oeffne Safari` oder `Oeffne die App Notizen`."
                ),
                detail="Tool-Aufruf unklar, keine Ausfuehrung",
            )
        return LegacyRoute(normalized_user_message, intent=intent)

    async def _decide_tool_intent(
        self,
        user_message: str,
        settings: dict[str, Any],
        allow_learned_commands: bool = True,
    ) -> ToolCallIntent | None:
        if allow_learned_commands:
            learned_intent = await self.learning_stage.learned_command(user_message)
            if learned_intent:
                return await self.learning.apply_adaptive_routing(learned_intent)

        heuristic_intent = self.heuristic.match(user_message)
        if heuristic_intent:
            return await self.learning.apply_adaptive_routing(heuristic_intent)

        if not self.enable_tool_planner:
            return heuristic_intent

        if not looks_like_tool_request(user_message):
            return heuristic_intent

        ranked_tool_specs = await self.learning.rank_tool_specs_for_planner(self.tools.list_specs())
        try:
            planned = await plan_tool_call(
                base_url=str(settings.get("ollama_base_url", "http://127.0.0.1:11434")),
                model=str(settings.get("model_name", "qwen2.5:3b-instruct")),
                user_message=user_message,
                tool_specs=ranked_tool_specs,
            )
        except Exception:
            return heuristic_intent

        if not planned:
            return heuristic_intent

        tool_name = str(planned.get("tool_name", "")).strip()
        tool_input = planned.get("tool_input")
        reason = str(planned.get("reason", "LLM Planner"))

        if not tool_name or not isinstance(tool_input, dict):
            return heuristic_intent

        if not self.tools.has_tool(tool_name):
            return heuristic_intent

        intent = ToolCallIntent(
            tool_name=tool_name,
            tool_input=tool_input,
            reason=reason,
        )
        return await self.learning.apply_adaptive_routing(intent)
