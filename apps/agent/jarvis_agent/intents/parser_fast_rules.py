from __future__ import annotations

from ..tool_intent import ToolCallIntent, infer_heuristic_tool_call


def parse_fast_rules(user_message: str) -> ToolCallIntent | None:
    intent = infer_heuristic_tool_call(user_message)
    if intent is None:
        return None

    intent.reason = f"FastRules: {intent.reason}"
    if intent.confidence <= 0:
        intent.confidence = 0.92
    return intent
