"""Order legacy stages and planner fallback; translate confirmation metadata."""

from __future__ import annotations

from typing import Any

from ..conversation_helpers import looks_like_tool_request, normalize_honorifics
from ..learning_engine import LearningEngine
from ..tool_intent import ToolCallIntent
from ..tools import ToolRegistry
from .legacy_planner import LegacyPlannerAdapter
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
        self.learning = learning
        self.responses = responses
        self.planner = LegacyPlannerAdapter(tools, learning, enable_tool_planner=enable_tool_planner)
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
                    "Ich habe den Befehl nicht eindeutig erkannt. "
                    "Welche konkrete Aktion meinst du?"
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

        # Preserve learned triggers first, but never infer actions from generic
        # mentions of files/reminders in an ordinary conversation.
        if not looks_like_tool_request(user_message):
            return None

        heuristic_intent = self.heuristic.match(user_message)
        if heuristic_intent:
            return await self.learning.apply_adaptive_routing(heuristic_intent)

        # An explicit unknown /tool request must not silently become a
        # *different* tool call through the optional language-model planner.
        if user_message.strip().lower().startswith("/tool "):
            return None

        return await self.planner.plan(user_message, settings)
