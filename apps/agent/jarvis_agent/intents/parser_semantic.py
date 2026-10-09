from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..app_aliases import normalize_app_name
from ..tool_intent import ToolCallIntent
from .context_resolver import IntentContext, resolve_pronoun_app


APP_ACTION_RE = re.compile(
    r"(?i)\b(?:schliess(?:e|en)?|schließe(?:n)?|beende|close|fokus(?:siere)?|focus)\s+"
    r"(?:die|den|das)?\s*([a-z0-9 ._-]{2,80})"
)
PROCESS_KILL_RE = re.compile(r"(?i)\b(?:beende|kill|stoppe|terminate)\s+(?:prozess|process)?\s*([a-z0-9._-]{1,80})")
PROCESS_PID_RE = re.compile(r"(?i)\bpid\s*(\d{1,8})\b")
FILE_SEARCH_RE = re.compile(r"(?i)\b(?:suche|finde|search)\b.*\b(?:datei|file)\b\s*(.+)$")
NOTIFICATION_RE = re.compile(
    r"(?is)\b(?:benachricht(?:ige|igung)|notification|notify)\b(?:\s+mit)?\s*[:\-]?\s*(.+)$"
)
SCHEDULE_RE = re.compile(
    r"(?is)\b(?:plane|erstelle|create)\s+(?:task|scheduled task|geplanten task)\s+"
    r"([a-z0-9 ._-]{2,80})\b.*?\b(?:um|at)\s*(\d{1,2}[:.]\d{2})\b.*?\b(?:cmd|befehl|command)\s*[:\-]?\s*(.+)$"
)
URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)


@dataclass
class SemanticParseResult:
    intent: ToolCallIntent | None
    missing_slots: list[str]
    detail: str


def _trim(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).strip(" ,.;:!?-")


def parse_semantic_intent(user_message: str, context: IntentContext) -> SemanticParseResult:
    message = _trim(user_message)
    lowered = message.lower()
    pronoun_target = resolve_pronoun_app(message, context)
    if not message:
        return SemanticParseResult(intent=None, missing_slots=[], detail="semantic-empty")

    if re.search(r"(?i)\b(?:laufende apps|running apps|aktive apps|geoeffnete apps)\b", message):
        return SemanticParseResult(
            intent=ToolCallIntent(
                tool_name="list_running_apps",
                tool_input={},
                reason="Semantic: App-Liste erkannt",
                confidence=0.86,
            ),
            missing_slots=[],
            detail="semantic-list-running-apps",
        )

    app_action = APP_ACTION_RE.search(message)
    if app_action:
        action_verb = app_action.group(0).lower()
        target_raw = _trim(app_action.group(1))
        target = normalize_app_name(target_raw)
        # Prefer context resolution for pronoun targets like "schliesse sie bitte".
        if pronoun_target and target_raw.lower().split(" ", 1)[0] in {"sie", "ihn", "it", "die", "diese"}:
            target = normalize_app_name(pronoun_target)
        if "fokus" in action_verb or "focus" in action_verb:
            return SemanticParseResult(
                intent=ToolCallIntent(
                    tool_name="focus_app",
                    tool_input={"app_name": target},
                    reason="Semantic: Fokus-App erkannt",
                    confidence=0.84,
                ),
                missing_slots=[],
                detail="semantic-focus-app",
            )
        return SemanticParseResult(
            intent=ToolCallIntent(
                tool_name="close_app",
                tool_input={"app_name": target},
                reason="Semantic: App schließen erkannt",
                confidence=0.84,
            ),
            missing_slots=[],
            detail="semantic-close-app",
        )

    if pronoun_target and re.search(r"(?i)\b(?:schliess(?:e|en)?|schließe(?:n)?|beende|close)\b", message):
        return SemanticParseResult(
            intent=ToolCallIntent(
                tool_name="close_app",
                tool_input={"app_name": normalize_app_name(pronoun_target)},
                reason="Semantic: Kontext-Pronomen auf letzte App aufgelöst",
                confidence=0.72,
            ),
            missing_slots=[],
            detail="semantic-close-app-context",
        )

    if re.search(r"(?i)\b(?:zeige|liste|list|show)\b.*\b(?:prozesse|processes)\b", message):
        return SemanticParseResult(
            intent=ToolCallIntent(
                tool_name="process_list",
                tool_input={"limit": 25},
                reason="Semantic: Prozessliste erkannt",
                confidence=0.8,
            ),
            missing_slots=[],
            detail="semantic-process-list",
        )

    process_kill = PROCESS_KILL_RE.search(message)
    if process_kill:
        process_ref = _trim(process_kill.group(1))
        pid_match = PROCESS_PID_RE.search(message)
        payload: dict[str, Any] = {"force": bool(re.search(r"(?i)\b(force|hart|sofort)\b", message))}
        if pid_match:
            payload["pid"] = int(pid_match.group(1))
        else:
            payload["name"] = process_ref
        return SemanticParseResult(
            intent=ToolCallIntent(
                tool_name="process_terminate",
                tool_input=payload,
                reason="Semantic: Prozess beenden erkannt",
                confidence=0.79,
            ),
            missing_slots=[],
            detail="semantic-process-terminate",
        )

    file_search = FILE_SEARCH_RE.search(message)
    if file_search:
        query = _trim(file_search.group(1))
        if not query:
            return SemanticParseResult(intent=None, missing_slots=["query"], detail="semantic-file-search-missing-query")
        return SemanticParseResult(
            intent=ToolCallIntent(
                tool_name="file_search",
                tool_input={"query": query, "limit": 20},
                reason="Semantic: Dateisuche erkannt",
                confidence=0.83,
            ),
            missing_slots=[],
            detail="semantic-file-search",
        )

    if re.search(r"(?i)\b(?:oeffne|öffne|open)\b", message):
        match_url = URL_RE.search(message)
        if match_url:
            return SemanticParseResult(
                intent=ToolCallIntent(
                    tool_name="open_url",
                    tool_input={"url": match_url.group(0)},
                    reason="Semantic: URL-Aktion erkannt",
                    confidence=0.78,
                ),
                missing_slots=[],
                detail="semantic-open-url",
            )

    notification = NOTIFICATION_RE.search(message)
    if notification:
        note_text = _trim(notification.group(1))
        if not note_text:
            return SemanticParseResult(intent=None, missing_slots=["text"], detail="semantic-notification-missing-text")
        return SemanticParseResult(
            intent=ToolCallIntent(
                tool_name="send_notification",
                tool_input={"title": "Jarvis", "text": note_text},
                reason="Semantic: Notification erkannt",
                confidence=0.81,
            ),
            missing_slots=[],
            detail="semantic-notification",
        )

    schedule = SCHEDULE_RE.search(message)
    if schedule:
        task_name = _trim(schedule.group(1))
        at_time = _trim(schedule.group(2)).replace(".", ":")
        command = _trim(schedule.group(3))
        missing: list[str] = []
        if not task_name:
            missing.append("task_name")
        if not at_time:
            missing.append("time")
        if not command:
            missing.append("command")
        if missing:
            return SemanticParseResult(intent=None, missing_slots=missing, detail="semantic-scheduler-missing-slots")
        return SemanticParseResult(
            intent=ToolCallIntent(
                tool_name="scheduler_create_task",
                tool_input={"task_name": task_name, "time": at_time, "command": command},
                reason="Semantic: Scheduler-Task erkannt",
                confidence=0.76,
            ),
            missing_slots=[],
            detail="semantic-scheduler-create",
        )

    if any(token in lowered for token in ("notiz", "note", "kalender", "calendar", "reminder", "erinnerung")):
        return SemanticParseResult(
            intent=None,
            missing_slots=["details"],
            detail="semantic-domain-detected-but-ambiguous",
        )

    return SemanticParseResult(intent=None, missing_slots=[], detail="semantic-no-match")
