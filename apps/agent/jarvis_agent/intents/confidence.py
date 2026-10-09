from __future__ import annotations

from ..tool_intent import ToolCallIntent


LOW_CONFIDENCE_THRESHOLD = 0.62


def clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def score_fast_intent(intent: ToolCallIntent) -> float:
    base = intent.confidence if intent.confidence > 0 else 0.92
    return clamp_confidence(base)


def score_semantic_intent(intent: ToolCallIntent, *, missing_slots: list[str]) -> float:
    base = intent.confidence if intent.confidence > 0 else 0.8
    if missing_slots:
        base -= min(0.35, 0.16 * len(missing_slots))
    if not intent.tool_name:
        base = min(base, 0.45)
    return clamp_confidence(base)


def build_clarification_question(*, tool_name: str | None, missing_slots: list[str]) -> str:
    if missing_slots:
        slot_hint = ", ".join(missing_slots[:2])
        return f"Bitte kurz praezisieren: Welche Details fuer `{slot_hint}` soll ich nutzen?"
    if tool_name:
        return f"Ich bin nicht sicher bei `{tool_name}`. Soll ich das genau so ausfuehren?"
    return "Soll ich den Befehl genauer ausfuehren, oder moechten Sie ihn praezisieren?"
