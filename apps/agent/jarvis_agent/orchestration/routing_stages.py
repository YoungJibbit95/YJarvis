"""Deterministic legacy stages: no lifecycle events or direct model I/O.

Learning keeps its existing injected action resolver for /learn. These are
compatibility boundaries, not V2 policy, plans or platform capability selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..conversation_helpers import (
    normalize_honorifics,
    quick_clarification_reply,
    quick_local_reply,
    quick_system_status_reply,
    quick_utility_reply,
)
from ..learning_engine import DecideToolIntentFn, LearningEngine
from ..safety import (
    confirmation_message,
    detect_blocked_user_request,
    detect_confirmation_required_request,
    is_confirmation_message,
    refusal_message,
)
from ..tool_intent import ToolCallIntent, infer_heuristic_tool_call
from ..tools import ToolRegistry


@dataclass(frozen=True)
class LegacyRoute:
    """An internal result: local reply, one legacy intent, or conversational fallback."""

    user_message: str
    reply: str | None = None
    detail: str = ""
    intent: ToolCallIntent | None = None


@dataclass(frozen=True)
class ConfirmationResolution:
    user_message: str
    was_policy_confirmed: bool = False


class LegacySafetyStage:
    def __init__(self) -> None:
        self.pending_confirmations: dict[str, dict[str, str]] = {}

    def resolve_confirmation(
        self, session_id: str, user_message: str, profile: dict[str, Any],
    ) -> ConfirmationResolution:
        pending_confirmation = self.pending_confirmations.get(session_id)
        if pending_confirmation:
            if is_confirmation_message(user_message, profile):
                original_message = pending_confirmation.get("original_message", user_message)
                self.pending_confirmations.pop(session_id, None)
                return ConfirmationResolution(original_message, was_policy_confirmed=True)
            self.pending_confirmations.pop(session_id, None)
        return ConfirmationResolution(user_message)

    def check(
        self, session_id: str, confirmation: ConfirmationResolution, profile: dict[str, Any],
    ) -> LegacyRoute | None:
        user_message = confirmation.user_message
        blocked_reason = detect_blocked_user_request(user_message, profile)
        if blocked_reason:
            return LegacyRoute(
                user_message,
                reply=normalize_honorifics(refusal_message(profile, reason=blocked_reason)),
                detail="Sicherheitsregel hat Anfrage blockiert",
            )

        if not confirmation.was_policy_confirmed:
            confirm_reason = detect_confirmation_required_request(user_message, profile)
            if confirm_reason:
                self.pending_confirmations[session_id] = {
                    "original_message": user_message,
                    "reason": confirm_reason,
                }
                return LegacyRoute(
                    user_message,
                    reply=normalize_honorifics(confirmation_message(profile, reason=confirm_reason)),
                    detail="Sicherheitsbestaetigung erforderlich",
                )
        return None


class LegacyLearningStage:
    def __init__(self, learning: LearningEngine) -> None:
        self.learning = learning

    async def instruction(
        self, user_message: str, settings: dict[str, Any], decide_tool_intent: DecideToolIntentFn,
    ) -> LegacyRoute | None:
        learning_response = await self.learning.handle_learning_instruction(
            user_message=user_message, settings=settings, decide_tool_intent=decide_tool_intent,
        )
        if learning_response:
            return LegacyRoute(
                user_message,
                reply=normalize_honorifics(learning_response),
                detail="Lernmodus aktualisiert",
            )
        return None

    async def learned_command(self, user_message: str) -> ToolCallIntent | None:
        return await self.learning.resolve_learned_command_intent(user_message)


class LocalFastPaths:
    def route(self, user_message: str, settings: dict[str, Any]) -> LegacyRoute | None:
        quick_reply = quick_local_reply(user_message)
        if quick_reply:
            return LegacyRoute(
                user_message,
                reply=normalize_honorifics(quick_reply),
                detail="Schnellantwort lokal",
            )

        quick_status = quick_system_status_reply(user_message, settings)
        if quick_status:
            return LegacyRoute(
                user_message,
                reply=normalize_honorifics(quick_status),
                detail="Statusantwort lokal",
            )

        quick_utility = quick_utility_reply(user_message)
        if quick_utility:
            return LegacyRoute(
                user_message,
                reply=normalize_honorifics(quick_utility),
                detail="Utility-Antwort lokal",
            )

        clarification = quick_clarification_reply(user_message)
        if clarification:
            return LegacyRoute(
                user_message,
                reply=normalize_honorifics(clarification),
                detail="Rueckfrage fuer praezisen Auftrag",
            )
        return None


class LegacyHeuristicFastPath:
    def __init__(self, tools: ToolRegistry) -> None:
        self.tools = tools

    def match(self, user_message: str) -> ToolCallIntent | None:
        heuristic_intent = infer_heuristic_tool_call(user_message)
        if heuristic_intent and self.tools.has_tool(heuristic_intent.tool_name):
            return heuristic_intent
        if heuristic_intent and not self.tools.has_tool(heuristic_intent.tool_name):
            heuristic_intent = None
        return heuristic_intent
