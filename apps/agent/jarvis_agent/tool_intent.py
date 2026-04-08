from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCallIntent:
    tool_name: str
    tool_input: dict[str, Any]
    reason: str


URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
EXPLICIT_TOOL_RE = re.compile(r"^/tool\s+([a-zA-Z0-9_\-]+)(?:\s+(.*))?$")
REMINDER_CONTENT_RE = re.compile(
    r"(?i)\b(?:die|dass sie|mit(?:\s+dem)?\s+(?:text|inhalt))\s*(?:sagt|lautet|heisst|heißt)?\s*[:,\-]?\s*(.+)$"
)
CALENDAR_CONTENT_RE = re.compile(
    r"(?i)\b(?:mit(?:\s+dem)?\s+titel|titel|inhalt|dass|die)\s*(?:sagt|lautet|heisst|heißt)?\s*[:,\-]?\s*(.+)$"
)
WEEKDAY_INDEX = {
    "montag": 0,
    "dienstag": 1,
    "mittwoch": 2,
    "donnerstag": 3,
    "freitag": 4,
    "samstag": 5,
    "sonntag": 6,
}
TRAILING_POLITE_WORDS_RE = re.compile(r"(?i)\b(?:bitte|jetzt|mal|gleich|danke|thanks?)\b$")
APP_FORBIDDEN_HINTS = (
    "http://",
    "https://",
    "zwischenablage",
    "clipboard",
    "datei",
    "file",
    "kalender",
    "calendar",
    "erinner",
)
CALENDAR_TEMPORAL_HINT_WORDS = (
    "heute",
    "morgen",
    "uebermorgen",
    "übermorgen",
    "montag",
    "dienstag",
    "mittwoch",
    "donnerstag",
    "freitag",
    "samstag",
    "sonntag",
)


def _extract_quoted(text: str) -> str | None:
    double_match = re.search(r"\"([^\"]+)\"", text)
    if double_match:
        return double_match.group(1).strip()

    single_match = re.search(r"'([^']+)'", text)
    if single_match:
        return single_match.group(1).strip()

    return None


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _trim_trailing_polite_words(text: str) -> str:
    trimmed = text.strip()
    while True:
        match = TRAILING_POLITE_WORDS_RE.search(trimmed)
        if not match:
            break
        trimmed = trimmed[: match.start()].strip()
    return trimmed.strip(" .,:;!?-")


def _safe_int(raw: str, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []

    ordered = sorted(spans, key=lambda item: item[0])
    merged: list[tuple[int, int]] = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
            continue
        merged.append((start, end))
    return merged


def _remove_spans(text: str, spans: list[tuple[int, int]]) -> str:
    if not spans:
        return text

    chars = list(text)
    for start, end in _merge_spans(spans):
        for index in range(max(0, start), min(len(chars), end)):
            chars[index] = " "
    return "".join(chars)


def _normalize_due_phrase(raw: str) -> str:
    phrase = _collapse_whitespace(raw.strip(" ,.;:-"))
    phrase = re.sub(r"(?i)^(?:auf|am|um|fuer|für|zum|zu)\s+", "", phrase)
    return _collapse_whitespace(phrase)


def _infer_open_app_name(message: str) -> str | None:
    patterns = (
        r"(?i)\b(?:oeffne|öffne|starte|start|launch)\s+(?:die\s+|den\s+|das\s+)?(?:app\s+)?(.+)$",
        r"(?i)\b(?:mach)\s+(?:die\s+|den\s+|das\s+)?(.+?)\s+auf\b",
    )

    for pattern in patterns:
        match = re.search(pattern, message)
        if not match:
            continue
        candidate = _trim_trailing_polite_words(_collapse_whitespace(match.group(1)))
        candidate = re.sub(r"(?i)^(?:app\s+)", "", candidate).strip()
        if not candidate:
            continue
        lowered = candidate.lower()
        if any(hint in lowered for hint in APP_FORBIDDEN_HINTS):
            continue
        if len(candidate) > 80:
            continue
        return candidate
    return None


def _infer_clipboard_write_text(message: str) -> str:
    quoted = _extract_quoted(message)
    if quoted:
        return quoted

    patterns = (
        r"(?is)\b(?:setze|schreibe|kopiere)\s+(.+?)\s+(?:in\s+die\s+)?zwischenablage\b",
        r"(?is)\bzwischenablage\b.*?\b(?:setze|schreibe|kopiere)\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if not match:
            continue
        candidate = _trim_trailing_polite_words(_collapse_whitespace(match.group(1)))
        if candidate:
            return candidate

    return _trim_trailing_polite_words(_collapse_whitespace(message))


def _extract_due_components(text: str) -> tuple[str | None, str | None, list[tuple[int, int]]]:
    now = datetime.now()
    spans: list[tuple[int, int]] = []
    due_phrase_parts: list[str] = []
    due_date = None
    day_was_explicit = False

    def _add_phrase_and_span(match: re.Match[str]) -> None:
        spans.append(match.span())
        phrase = _normalize_due_phrase(match.group(0))
        if phrase:
            due_phrase_parts.append(phrase)

    date_match = re.search(
        r"(?i)\b(?:(?:auf|am|fuer|für|zum|zu)\s+)?(\d{1,2}\.\d{1,2}(?:\.\d{2,4})?)\b",
        text,
    )
    if date_match:
        raw_date = date_match.group(1)
        day_str, month_str, *year_part = raw_date.split(".")
        day = int(day_str)
        month = int(month_str)
        year = int(year_part[0]) if year_part else now.year
        if year < 100:
            year += 2000
        try:
            due_date = datetime(year=year, month=month, day=day).date()
            if not year_part and due_date < now.date():
                due_date = datetime(year=year + 1, month=month, day=day).date()
            day_was_explicit = True
            _add_phrase_and_span(date_match)
        except ValueError:
            due_date = None

    if due_date is None:
        relative_patterns = (
            (r"(?i)\b(?:auf\s+)?(?:übermorgen|uebermorgen)\b", 2),
            (r"(?i)\b(?:auf\s+)?morgen\b", 1),
            (r"(?i)\b(?:auf\s+)?heute\b", 0),
        )
        for pattern, offset in relative_patterns:
            relative_match = re.search(pattern, text)
            if not relative_match:
                continue
            due_date = (now + timedelta(days=offset)).date()
            day_was_explicit = True
            _add_phrase_and_span(relative_match)
            break

    if due_date is None:
        weekday_match = re.search(
            r"(?i)\b(?:(?:am|auf)\s+)?(?:(naechsten|nächsten)\s+)?"
            r"(montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b",
            text,
        )
        if weekday_match:
            qualifier = (weekday_match.group(1) or "").lower()
            weekday_name = weekday_match.group(2).lower()
            target_weekday = WEEKDAY_INDEX[weekday_name]
            days_ahead = (target_weekday - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            if qualifier in {"naechsten", "nächsten"} and days_ahead < 7:
                days_ahead += 7
            due_date = (now + timedelta(days=days_ahead)).date()
            day_was_explicit = True
            _add_phrase_and_span(weekday_match)

    hour = 9
    minute = 0
    has_explicit_time = False
    time_match = re.search(r"(?i)\b(?:um\s+)?(\d{1,2})(?:[:\.](\d{1,2}))?\s*uhr\b", text)
    if time_match:
        parsed_hour = int(time_match.group(1))
        parsed_minute = int(time_match.group(2) or "0")
        if 0 <= parsed_hour <= 23 and 0 <= parsed_minute <= 59:
            hour = parsed_hour
            minute = parsed_minute
            has_explicit_time = True
            _add_phrase_and_span(time_match)

    if due_date is None and has_explicit_time:
        due_date = now.date()

    if due_date is None:
        return None, None, spans

    due_at = datetime(
        year=due_date.year,
        month=due_date.month,
        day=due_date.day,
        hour=hour,
        minute=minute,
    )

    if not day_was_explicit and due_at <= now:
        due_at = due_at + timedelta(days=1)

    unique_parts: list[str] = []
    seen: set[str] = set()
    for part in due_phrase_parts:
        lowered = part.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_parts.append(part)
    due_phrase = _collapse_whitespace(" ".join(unique_parts))
    return due_at.isoformat(timespec="minutes"), due_phrase or None, spans


def _clean_reminder_title(value: str) -> str:
    cleaned = value
    cleaned = re.sub(r"(?i)\bjarvis\b[:,]?", " ", cleaned)
    cleaned = re.sub(r"(?i)\b(?:bitte|mach(?:\s+mir)?|erstell(?:e)?(?:\s+mir)?|lege(?:\s+mir)?(?:\s+an)?|setze(?:\s+mir)?)\b", " ", cleaned)
    cleaned = re.sub(r"(?i)\b(?:eine?|nen|ne)\s+erinnerung\b", " ", cleaned)
    cleaned = re.sub(r"(?i)\berinnerung\b", " ", cleaned)
    cleaned = re.sub(r"(?i)\berinner(?:e)?\s+mich(?:\s+daran)?\b", " ", cleaned)
    cleaned = re.sub(r"(?i)\b(?:die|dass sie|mit(?:\s+dem)?\s+(?:text|inhalt)|sagt|lautet|heisst|heißt)\b", " ", cleaned)
    cleaned = re.sub(r"[,;:]+", " ", cleaned)
    cleaned = _collapse_whitespace(cleaned.strip(" .-"))
    return cleaned


def _build_reminder_title(
    *,
    original_message: str,
    title_candidate_message: str,
    due_phrase: str | None,
) -> str:
    explicit_content = REMINDER_CONTENT_RE.search(title_candidate_message)
    if explicit_content:
        title = _clean_reminder_title(explicit_content.group(1))
    else:
        quoted = _extract_quoted(original_message)
        if quoted:
            title = _clean_reminder_title(quoted)
        else:
            title = _clean_reminder_title(title_candidate_message)

    if not title:
        title = "Neue Erinnerung"

    if due_phrase:
        normalized_title = title.lower()
        normalized_due = due_phrase.lower()
        if normalized_due not in normalized_title:
            title = _collapse_whitespace(f"{title} {due_phrase}")

    return title


def _infer_reminder_tool_input(message: str) -> dict[str, Any]:
    due_at, due_phrase, spans = _extract_due_components(message)
    message_without_due = _remove_spans(message, spans)
    title = _build_reminder_title(
        original_message=message,
        title_candidate_message=message_without_due,
        due_phrase=due_phrase,
    )

    payload: dict[str, Any] = {"title": title}
    if due_at:
        payload["due_at"] = due_at
    return payload


def _extract_duration_minutes(text: str) -> tuple[int | None, list[tuple[int, int]]]:
    minute_match = re.search(
        r"(?i)\b(?:fuer|für|dauer(?:\s+von)?)\s+(\d{1,3})\s*(?:min|mins?|minute|minuten)\b",
        text,
    )
    if minute_match:
        minutes = _safe_int(minute_match.group(1), 60)
        if 1 <= minutes <= 24 * 60:
            return minutes, [minute_match.span()]

    hour_match = re.search(
        r"(?i)\b(?:fuer|für|dauer(?:\s+von)?)\s+(\d{1,2})(?:[.,](\d{1,2}))?\s*(?:h|std|stunde|stunden)\b",
        text,
    )
    if hour_match:
        hours = _safe_int(hour_match.group(1), 1)
        decimals = hour_match.group(2) or "0"
        minute_fraction = _safe_int(decimals, 0)
        if len(decimals) == 1:
            minute_fraction *= 10
        duration = int(hours * 60 + (minute_fraction / 100.0) * 60)
        duration = max(1, min(duration, 24 * 60))
        return duration, [hour_match.span()]

    return None, []


def _clean_calendar_title(value: str) -> str:
    cleaned = value
    cleaned = re.sub(r"(?i)\bjarvis\b[:,]?", " ", cleaned)
    cleaned = re.sub(
        r"(?i)\b(?:bitte|mach(?:\s+mir)?|erstell(?:e)?(?:\s+mir)?|lege(?:\s+mir)?(?:\s+an)?|"
        r"setze(?:\s+mir)?|plan(?:e)?(?:\s+mir)?|trag(?:e)?(?:\s+mir)?(?:\s+ein)?)\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"(?i)\b(?:einen|einem|einer|ein|neuen?)\s+(?:termin|kalendereintrag|event)\b", " ", cleaned)
    cleaned = re.sub(r"(?i)\b(?:kalender|calendar|termin|eintrag|event)\b", " ", cleaned)
    cleaned = re.sub(r"(?i)\b(?:in\s+den|im)\s+kalender\b", " ", cleaned)
    cleaned = re.sub(r"(?i)\beintragen\b", " ", cleaned)
    cleaned = re.sub(r"(?i)\b(?:mit(?:\s+dem)?\s+titel|titel|inhalt|dass|die|sagt|lautet|heisst|heißt)\b", " ", cleaned)
    cleaned = re.sub(r"[,;:]+", " ", cleaned)
    cleaned = _trim_trailing_polite_words(_collapse_whitespace(cleaned.strip(" .-")))
    return cleaned


def _build_calendar_title(*, original_message: str, title_candidate_message: str) -> str:
    quoted = _extract_quoted(original_message)
    if quoted:
        title = _clean_calendar_title(quoted)
    else:
        explicit_content = CALENDAR_CONTENT_RE.search(title_candidate_message)
        if explicit_content:
            title = _clean_calendar_title(explicit_content.group(1))
        else:
            title = _clean_calendar_title(title_candidate_message)

    if not title:
        return "Neuer Termin"
    return title


def _infer_calendar_tool_input(message: str) -> dict[str, Any]:
    start_at, _, date_spans = _extract_due_components(message)
    duration_minutes, duration_spans = _extract_duration_minutes(message)

    title_source = _remove_spans(message, [*date_spans, *duration_spans])
    title = _build_calendar_title(
        original_message=message,
        title_candidate_message=title_source,
    )

    payload: dict[str, Any] = {
        "title": title,
        "duration_minutes": duration_minutes or 60,
    }

    if start_at:
        payload["start_at"] = start_at
    else:
        payload["start_offset_minutes"] = 5

    return payload


def _looks_like_calendar_request(lowered_message: str) -> bool:
    has_calendar_context = any(keyword in lowered_message for keyword in ["kalender", "calendar"])
    has_event_noun = any(keyword in lowered_message for keyword in ["termin", "eintrag", "event"])
    has_event_verb = any(keyword in lowered_message for keyword in ["plane", "plan ", "eintragen", "trag ", "schedule"])
    has_temporal_hint = (
        any(keyword in lowered_message for keyword in CALENDAR_TEMPORAL_HINT_WORDS)
        or re.search(r"(?i)\b\d{1,2}(?::|\.)?\d{0,2}\s*uhr\b", lowered_message) is not None
        or re.search(r"(?i)\b\d{1,2}\.\d{1,2}(?:\.\d{2,4})?\b", lowered_message) is not None
    )

    if has_calendar_context and (has_event_noun or has_event_verb):
        return True

    if has_event_noun and has_event_verb and has_temporal_hint:
        return True

    return False


def parse_explicit_tool_call(user_message: str) -> ToolCallIntent | None:
    match = EXPLICIT_TOOL_RE.match(user_message.strip())
    if not match:
        return None

    tool_name = match.group(1)
    payload_raw = (match.group(2) or "{}").strip()
    if not payload_raw:
        payload_raw = "{}"

    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    return ToolCallIntent(
        tool_name=tool_name,
        tool_input=payload,
        reason="Expliziter /tool Aufruf",
    )


def infer_heuristic_tool_call(user_message: str) -> ToolCallIntent | None:
    message = user_message.strip()
    lowered = message.lower()

    explicit = parse_explicit_tool_call(message)
    if explicit:
        return explicit

    url_match = URL_RE.search(message)
    if url_match and ("oeffne" in lowered or "öffne" in lowered):
        return ToolCallIntent(
            tool_name="open_url",
            tool_input={"url": url_match.group(0)},
            reason="URL oeffnen erkannt",
        )

    app_name = _infer_open_app_name(message)
    if app_name:
        return ToolCallIntent(
            tool_name="open_app",
            tool_input={"app_name": app_name},
            reason="App oeffnen erkannt",
        )

    if "zwischenablage" in lowered and ("lesen" in lowered or "zeige" in lowered):
        return ToolCallIntent(
            tool_name="clipboard_read",
            tool_input={},
            reason="Clipboard Read erkannt",
        )

    if "zwischenablage" in lowered and any(
        keyword in lowered for keyword in ["setze", "schreibe", "kopiere"]
    ):
        text_value = _infer_clipboard_write_text(message)
        return ToolCallIntent(
            tool_name="clipboard_write",
            tool_input={"text": text_value},
            reason="Clipboard Write erkannt",
        )

    if any(trigger in lowered for trigger in ["erinnerung", "erinner mich", "remind me"]):
        return ToolCallIntent(
            tool_name="reminder_create",
            tool_input=_infer_reminder_tool_input(message),
            reason="Erinnerung erstellen erkannt",
        )

    if _looks_like_calendar_request(lowered):
        return ToolCallIntent(
            tool_name="calendar_create_event",
            tool_input=_infer_calendar_tool_input(message),
            reason="Kalender Event erkannt",
        )

    read_match = re.search(r"(?:datei\s+lesen|read\s+file)\s+(.+)$", message, re.IGNORECASE)
    if read_match:
        return ToolCallIntent(
            tool_name="file_read",
            tool_input={"path": read_match.group(1).strip()},
            reason="Datei lesen erkannt",
        )

    write_match = re.search(
        r"(?:datei\s+schreiben|write\s+file)\s+([^:]+):\s*(.+)$",
        message,
        re.IGNORECASE | re.DOTALL,
    )
    if write_match:
        return ToolCallIntent(
            tool_name="file_write",
            tool_input={
                "path": write_match.group(1).strip(),
                "content": write_match.group(2),
                "mode": "overwrite",
            },
            reason="Datei schreiben erkannt",
        )

    return None
