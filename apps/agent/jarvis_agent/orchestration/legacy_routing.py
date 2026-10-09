"""Order legacy stages and planner fallback; translate confirmation metadata."""

from __future__ import annotations

from typing import Any

from ..conversation_helpers import looks_like_tool_request, normalize_honorifics
from ..learning_engine import LearningEngine
from ..tool_intent import ToolCallIntent
from ..tools import ToolRegistry
from .legacy_planner import LegacyPlannerAdapter
from .reminder_clarification import ReminderClarifications
from .semantic_pilot import SemanticDecision, eligible_for_pilot
from .legacy_responses import LegacyResponses
from .routing_stages import (
    ConfirmationResolution,
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
        self.reminder_clarifications = ReminderClarifications()

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

        # A reminder follow-up is scoped to this session, and may only complete
        # the single field originally requested. A different learned command
        # always wins rather than becoming accidental reminder content.
        if self.reminder_clarifications.has_pending(session_id):
            learned_followup = await self.learning_stage.learned_command(normalized_user_message)
            if learned_followup:
                self.reminder_clarifications.clear(session_id)
            else:
                resumed = self.reminder_clarifications.consume(session_id, normalized_user_message)
                if resumed:
                    if resumed.intent and resumed.full_request:
                        # Re-evaluate the assembled user request under the same
                        # configured policy before ordinary Tool Approval.
                        verified = self.safety.check(
                            session_id,
                            ConfirmationResolution(
                                resumed.full_request, confirmation.was_policy_confirmed,
                            ),
                            profile,
                        )
                        if verified:
                            return verified
                        if self.heuristic.tools.has_tool(resumed.intent.tool_name):
                            return LegacyRoute(resumed.full_request, intent=resumed.intent)
                        return LegacyRoute(
                            resumed.full_request,
                            reply="Diese Erinnerungsfunktion ist hier nicht verfügbar.",
                            detail="Erinnerungstool nicht registriert",
                        )
                    return LegacyRoute(
                        normalized_user_message,
                        reply=resumed.reply,
                        detail="Rueckfrage zur Erinnerung",
                    )

        learning_route = await self.learning_stage.instruction(
            normalized_user_message, settings, self._decide_tool_intent,
        )
        if learning_route is not None:
            return learning_route

        local_route = self.local.route(normalized_user_message, settings)
        if local_route is not None:
            if local_route.detail == "Rueckfrage fuer praezisen Auftrag" and local_route.reply:
                self.reminder_clarifications.begin(
                    session_id, normalized_user_message, local_route.reply,
                )
            return local_route

        decision = await self._decide_tool_intent(normalized_user_message, settings)
        if isinstance(decision, SemanticDecision):
            if decision.kind == "tool" and decision.intent:
                return LegacyRoute(normalized_user_message, intent=decision.intent)
            if decision.kind == "clarify" and decision.question:
                return LegacyRoute(
                    normalized_user_message,
                    reply=decision.question,
                    detail="Rueckfrage des Semantic-Pilots",
                )
            # The model explicitly selected conversation, not any OS action.
            return LegacyRoute(normalized_user_message)
        intent = decision
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
    ) -> ToolCallIntent | SemanticDecision | None:
        if allow_learned_commands:
            learned_intent = await self.learning_stage.learned_command(user_message)
            if learned_intent:
                return await self.learning.apply_adaptive_routing(learned_intent)

        # Learned triggers remain first. This guard excludes conversational
        # questions, but also recognizes the complete existing deterministic
        # heuristic inventory (not only a shorter verb list), so no valid
        # legacy ToolIntent gets dropped before the registered-tool match.
        deterministic_candidate = looks_like_tool_request(user_message)
        if deterministic_candidate:
            heuristic_intent = self.heuristic.match(user_message)
            if heuristic_intent:
                return await self.learning.apply_adaptive_routing(heuristic_intent)
        elif not eligible_for_pilot(user_message):
            return None

        # An explicit unknown /tool request must not silently become a
        # *different* tool call through the optional language-model planner.
        if user_message.strip().lower().startswith("/tool "):
            return None

        # /learn resolution remains deterministic: do not persist an unverified
        # model interpretation as a reusable learned command.
        if not allow_learned_commands:
            return None

        return await self.planner.plan(user_message, settings)
