from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


OPENED_APP_RE = re.compile(r"(?i)\bapp geoeffnet:\s*([^\n(]+)")
OPEN_CMD_RE = re.compile(r"(?i)\b(?:oeffne|öffne|starte|open)\s+(?:die|den|das)?\s*([a-z0-9 ._-]{2,80})")
URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)


@dataclass
class IntentContext:
    last_app_name: str | None = None
    last_url: str | None = None


def _sanitize_candidate(value: str) -> str:
    candidate = re.sub(r"\s+", " ", str(value or "").strip())
    return candidate.strip(" ,.;:!?-")


def resolve_context(recent_messages: list[dict[str, Any]]) -> IntentContext:
    context = IntentContext()
    for row in reversed(recent_messages):
        content = str(row.get("content", "")).strip()
        if not content:
            continue

        if context.last_app_name is None:
            opened_app = OPENED_APP_RE.search(content)
            if opened_app:
                context.last_app_name = _sanitize_candidate(opened_app.group(1))
            else:
                open_cmd = OPEN_CMD_RE.search(content)
                if open_cmd:
                    context.last_app_name = _sanitize_candidate(open_cmd.group(1))

        if context.last_url is None:
            match_url = URL_RE.search(content)
            if match_url:
                context.last_url = match_url.group(0).strip()

        if context.last_app_name and context.last_url:
            break

    return context


def resolve_pronoun_app(message: str, context: IntentContext) -> str | None:
    lowered = message.lower()
    if not any(token in lowered for token in ("sie", "ihn", "diese app", "die app", "that app", "it")):
        return None
    return context.last_app_name
