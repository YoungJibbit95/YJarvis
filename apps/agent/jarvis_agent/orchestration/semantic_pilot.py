"""Small, deliberately fail-closed boundary for model-suggested legacy tools.

The tool_specs fields are only type hints; this pilot uses explicit validators.
The legacy registry and its normal approval lifecycle remain authoritative.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from ..conversation_helpers import looks_like_tool_request, strip_jarvis_prefix
from ..tool_intent import ToolCallIntent

# All five tools currently execute through macOS 'open' or AppleScript.
PILOT_TOOL_NAMES = frozenset({
    "open_app", "open_url", "reminder_list", "calendar_list_events", "notes_search",
})
_SAFE_QUESTION = re.compile(
    r"(?i)^(?:welche[rsn]?|was|wie|wann|wo|worauf|woran|"
    r"kannst du|könntest du|koenntest du)\b"
)
_SEMANTIC_VERB = re.compile(
    r"(?i)^(?:bitte[\s,]+)?(?:kannst du (?:bitte )?|"
    r"koenntest du (?:bitte )?|könntest du (?:bitte )?)?"
    r"(?:aktiviere|aktivier|rufe|ruf|wechsle|gehe|geh|schau|"
    r"zeige|zeig|such|durchsuche)\b"
)
_PILOT_TARGET = re.compile(
    r"(?i)\b(?:app|anwendung|programm|safari|browser|notiz|notizen|notes|"
    r"erinnerungen|reminders|kalender|termine|events)\b|https?://"
)
_QUESTION_INJECTION = re.compile(
    r"(?i)\b(?:passwort|kennwort|token|sudo|schlüssel|schluessel|"
    r"privat(?:e|er|en)?|freigabe|bestätige|bestaetige)\b"
)


@dataclass(frozen=True)
class SemanticDecision:
    kind: str  # tool, clarify, or conversation
    intent: ToolCallIntent | None = None
    question: str | None = None


def supported_legacy_platform() -> bool:
    """Do not advertise macOS-only legacy subprocesses as Windows providers."""
    return sys.platform == "darwin"


def eligible_for_pilot(message: str) -> bool:
    request = strip_jarvis_prefix(message).strip()
    if not request or len(request) > 350 or request.lower().startswith("/tool"):
        return False
    if looks_like_tool_request(request):
        return True
    return _SEMANTIC_VERB.match(request) is not None and _PILOT_TARGET.search(request) is not None


def _grounded_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text, re.IGNORECASE))


def _bounded_int(value: Any, original: str, default: int, max_value: int) -> int | None:
    if type(value) is not int or value < 1 or value > max_value:
        return None
    if value != default and not re.search(r"(?<!\d)" + str(value) + r"(?!\d)", original):
        return None
    return value


def _validate_tool_fields(name: str, args: dict[str, Any], original: str) -> dict[str, Any] | None:
    text = original.lower()

    if name == "open_app":
        if set(args) != {"app_name"}:
            return None
        app = args["app_name"]
        if not isinstance(app, str) or not 1 <= len(app.strip()) <= 80:
            return None
        if any(char in app for char in "\n\r/\0") or not _grounded_phrase(original, app.strip()):
            return None
        if not re.search(r"(?i)\b(?:app|öffne|oeffne|starte|aktivier|launch|open|programm)\b", original):
            return None
        return {"app_name": app.strip()}

    if name == "open_url":
        if set(args) != {"url"}:
            return None
        url = args["url"]
        if not isinstance(url, str) or not 1 <= len(url) <= 2048 or url not in original:
            return None
        if re.search(r"[\s\\\x00-\x1f]", url):
            return None
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                return None
            _ = parsed.port  # reject invalid port
        except ValueError:
            return None
        return {"url": url}

    if name == "reminder_list":
        if not re.search(r"\b(?:erinnerungen|reminders)\b", text):
            return None
        if not re.search(r"\b(?:zeig|zeige|liste|list|finde|such|offene|überblick|ueberblick)\b", text):
            return None
        if not set(args) <= {"limit"}:
            return None
        limit = args.get("limit", 8)
        checked = _bounded_int(limit, original, 8, 25)
        return {"limit": checked} if checked is not None else None

    if name == "calendar_list_events":
        if not re.search(r"\b(?:kalender|termine|events)\b", text):
            return None
        if not re.search(r"\b(?:zeig|zeige|liste|list|kommende|suche|such|überblick|ueberblick)\b", text):
            return None
        if not set(args) <= {"days_ahead", "limit"}:
            return None
        days = _bounded_int(args.get("days_ahead", 7), original, 7, 60)
        limit = _bounded_int(args.get("limit", 10), original, 10, 30)
        return {"days_ahead": days, "limit": limit} if days is not None and limit is not None else None

    if name == "notes_search":
        if not re.search(r"\b(?:notiz|notizen|notes|note)\b", text):
            return None
        if not re.search(r"\b(?:suche|such|finde|zeige|zeig|durchsuche|search)\b", text):
            return None
        if not set(args) <= {"query", "limit"} or "query" not in args:
            return None
        query = args["query"]
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 160:
            return None
        if "\n" in query or "\r" in query or not _grounded_phrase(original, query.strip()):
            return None
        limit = _bounded_int(args.get("limit", 8), original, 8, 25)
        return {"query": query.strip(), "limit": limit} if limit is not None else None

    return None


def validate_semantic_decision(
    proposed: Any, original: str, registered: set[str],
) -> SemanticDecision | None:
    """Never trust the LLM's tool name, reason, schema or invented target."""
    if not isinstance(proposed, dict):
        return None
    kind = proposed.get("decision")
    if kind == "conversation" and set(proposed) == {"decision"}:
        return SemanticDecision(kind="conversation")
    if kind == "clarify" and set(proposed) == {"decision", "question"}:
        question = proposed["question"]
        if not isinstance(question, str):
            return None
        if not 8 <= len(question) <= 140 or question.count("?") != 1:
            return None
        if question[-1] != "?" or "\n" in question or "\r" in question:
            return None
        if not _SAFE_QUESTION.match(question) or _QUESTION_INJECTION.search(question):
            return None
        return SemanticDecision(kind="clarify", question=question)
    if kind != "tool" or set(proposed) != {"decision", "tool_name", "tool_input"}:
        return None
    tool_name, tool_input = proposed["tool_name"], proposed["tool_input"]
    if not isinstance(tool_name, str) or tool_name not in PILOT_TOOL_NAMES or tool_name not in registered:
        return None
    if not isinstance(tool_input, dict):
        return None
    bounded = _validate_tool_fields(tool_name, tool_input, original)
    if bounded is None:
        return None
    return SemanticDecision(
        kind="tool",
        intent=ToolCallIntent(tool_name, bounded, "Validierter lokaler Semantic-Pilot"),
    )
