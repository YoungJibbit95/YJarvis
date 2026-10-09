from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from ..tool_intent import ToolCallIntent
from .confidence import (
    LOW_CONFIDENCE_THRESHOLD,
    build_clarification_question,
    clamp_confidence,
    score_fast_intent,
    score_semantic_intent,
)
from .context_resolver import resolve_context
from .parser_fast_rules import parse_fast_rules
from .parser_semantic import parse_semantic_intent


PlannerFn = Callable[[str], Awaitable[ToolCallIntent | None]]


@dataclass
class RoutedIntentDecision:
    intent: ToolCallIntent | None
    confidence: float
    stage: str
    clarification_question: str | None = None
    missing_slots: list[str] | None = None


async def route_intent(
    *,
    user_message: str,
    recent_messages: list[dict[str, object]] | None = None,
    planner_fn: PlannerFn | None = None,
) -> RoutedIntentDecision:
    recent_messages = recent_messages or []

    fast_intent = parse_fast_rules(user_message)
    if fast_intent is not None:
        confidence = score_fast_intent(fast_intent)
        fast_intent.confidence = confidence
        return RoutedIntentDecision(
            intent=fast_intent,
            confidence=confidence,
            stage="fast_rules",
        )

    context = resolve_context(recent_messages)
    semantic = parse_semantic_intent(user_message, context)
    if semantic.intent is not None:
        confidence = score_semantic_intent(semantic.intent, missing_slots=semantic.missing_slots)
        semantic.intent.confidence = confidence
        if confidence >= LOW_CONFIDENCE_THRESHOLD:
            return RoutedIntentDecision(
                intent=semantic.intent,
                confidence=confidence,
                stage="semantic",
                missing_slots=semantic.missing_slots,
            )
    elif semantic.missing_slots or semantic.detail.startswith("semantic-domain-detected"):
        return RoutedIntentDecision(
            intent=None,
            confidence=0.35,
            stage="semantic_low_confidence",
            clarification_question=build_clarification_question(
                tool_name=None,
                missing_slots=semantic.missing_slots or ["details"],
            ),
            missing_slots=semantic.missing_slots or ["details"],
        )

    if planner_fn is not None:
        planned_intent = await planner_fn(user_message)
        if planned_intent is not None:
            planned_confidence = clamp_confidence(max(0.66, planned_intent.confidence))
            planned_intent.confidence = planned_confidence
            return RoutedIntentDecision(
                intent=planned_intent,
                confidence=planned_confidence,
                stage="llm_planner",
            )

    if semantic.intent is not None:
        low_confidence = score_semantic_intent(semantic.intent, missing_slots=semantic.missing_slots)
        return RoutedIntentDecision(
            intent=None,
            confidence=low_confidence,
            stage="semantic_low_confidence",
            clarification_question=build_clarification_question(
                tool_name=semantic.intent.tool_name,
                missing_slots=semantic.missing_slots,
            ),
            missing_slots=semantic.missing_slots,
        )

    return RoutedIntentDecision(
        intent=None,
        confidence=0.0,
        stage="no_match",
        clarification_question=None,
        missing_slots=[],
    )
