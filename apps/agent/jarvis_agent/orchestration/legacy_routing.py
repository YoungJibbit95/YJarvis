"""Keep legacy safety, reply precedence and intent selection together for YJ2-03.

This adapter is deliberately not the YJ2-04 router/fast-path/planner redesign.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..conversation_helpers import (
    looks_like_tool_request,
    normalize_honorifics,
    quick_clarification_reply,
    quick_local_reply,
    quick_system_status_reply,
    quick_utility_reply,
)
from ..learning_engine import LearningEngine
from ..llm import plan_tool_call
from ..safety import (
    confirmation_message,
    detect_blocked_user_request,
    detect_confirmation_required_request,
    is_confirmation_message,
    refusal_message,
)
from ..tool_intent import ToolCallIntent, infer_heuristic_tool_call
from ..tools import ToolRegistry
from .legacy_responses import LegacyResponses


@dataclass(frozen=True)
class LegacyRoute:
    """An internal result: local reply, one legacy intent, or conversational fallback."""

    user_message: str
    reply: str | None = None
    detail: str = ""
    intent: ToolCallIntent | None = None


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
        self.pending_confirmations: dict[str, dict[str, str]] = {}

    async def route(
        self,
        session_id: str,
        run_id: str,
        user_message: str,
        profile: dict[str, Any],
        settings: dict[str, Any],
    ) -> LegacyRoute:
        normalized_user_message = user_message
        was_policy_confirmed = False

        pending_confirmation = self.pending_confirmations.get(session_id)
        if pending_confirmation:
            if is_confirmation_message(user_message, profile):
                normalized_user_message = pending_confirmation.get("original_message", user_message)
                was_policy_confirmed = True
                self.pending_confirmations.pop(session_id, None)
                await self.responses.emit_state(
                    session_id=session_id,
                    run_id=run_id,
                    state="thinking",
                    detail="Sicherheitsbestaetigung akzeptiert",
                )
            else:
                self.pending_confirmations.pop(session_id, None)

        blocked_reason = detect_blocked_user_request(normalized_user_message, profile)
        if blocked_reason:
            return LegacyRoute(
                normalized_user_message,
                reply=normalize_honorifics(refusal_message(profile, reason=blocked_reason)),
                detail="Sicherheitsregel hat Anfrage blockiert",
            )

        if not was_policy_confirmed:
            confirm_reason = detect_confirmation_required_request(normalized_user_message, profile)
            if confirm_reason:
                self.pending_confirmations[session_id] = {
                    "original_message": normalized_user_message,
                    "reason": confirm_reason,
                }
                return LegacyRoute(
                    normalized_user_message,
                    reply=normalize_honorifics(confirmation_message(profile, reason=confirm_reason)),
                    detail="Sicherheitsbestaetigung erforderlich",
                )

        learning_response = await self.learning.handle_learning_instruction(
            user_message=normalized_user_message,
            settings=settings,
            decide_tool_intent=self._decide_tool_intent,
        )
        if learning_response:
            return LegacyRoute(
                normalized_user_message,
                reply=normalize_honorifics(learning_response),
                detail="Lernmodus aktualisiert",
            )

        quick_reply = quick_local_reply(normalized_user_message)
        if quick_reply:
            return LegacyRoute(
                normalized_user_message,
                reply=normalize_honorifics(quick_reply),
                detail="Schnellantwort lokal",
            )

        quick_status = quick_system_status_reply(normalized_user_message, settings)
        if quick_status:
            return LegacyRoute(
                normalized_user_message,
                reply=normalize_honorifics(quick_status),
                detail="Statusantwort lokal",
            )

        quick_utility = quick_utility_reply(normalized_user_message)
        if quick_utility:
            return LegacyRoute(
                normalized_user_message,
                reply=normalize_honorifics(quick_utility),
                detail="Utility-Antwort lokal",
            )

        clarification = quick_clarification_reply(normalized_user_message)
        if clarification:
            return LegacyRoute(
                normalized_user_message,
                reply=normalize_honorifics(clarification),
                detail="Rueckfrage fuer praezisen Auftrag",
            )

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
            learned_intent = await self.learning.resolve_learned_command_intent(user_message)
            if learned_intent:
                return await self.learning.apply_adaptive_routing(learned_intent)

        heuristic_intent = infer_heuristic_tool_call(user_message)
        if heuristic_intent and self.tools.has_tool(heuristic_intent.tool_name):
            return await self.learning.apply_adaptive_routing(heuristic_intent)
        if heuristic_intent and not self.tools.has_tool(heuristic_intent.tool_name):
            heuristic_intent = None

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
