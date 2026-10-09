"""One-session, one-missing-field reminder clarification; no persistence or new tools."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from ..conversation_helpers import looks_like_tool_request, strip_jarvis_prefix
from ..tool_intent import ToolCallIntent, _extract_due_components

_REMINDER_WITH_TITLE = re.compile(
    r"(?i)^erinner(?:e)?\s+mich\s+an\s+(?:(?:den|die|das)\s+)?(.+?)\s*[.!?]?$"
)
_DAY = (
    r"(?:heute|morgen|übermorgen|uebermorgen|"
    r"(?:am\s+)?(?:nächsten\s+|naechsten\s+)?"
    r"(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)|"
    r"(?:am\s+)?\d{1,2}\.\d{1,2}(?:\.\d{2,4})?)"
)
_CLOCK = r"(?:um\s+)?(?:[01]?\d|2[0-3])(?::[0-5]\d|\.[0-5]\d)?\s+uhr"
_TIME_REPLY_RE = re.compile(rf"(?i)^(?:bitte\s+)?{_DAY}\s+{_CLOCK}\s*[.!?]?$")
_DAY_FRAGMENT = re.compile(rf"(?i)\b{_DAY}\b")
_CLOCK_FRAGMENT = re.compile(rf"(?i)\b{_CLOCK}\b")
_CANCEL = re.compile(
    r"(?i)^(?:abbrechen|abbruch|stopp|stop|vergiss es|vergiss die erinnerung|"
    r"doch nicht|nein danke|lass es|egal)[.!?]?$"
)
_TOPIC_CHANGE = re.compile(
    r"(?i)^(?:ach egal\b|anderes thema\b|vergiss das\b|"
    r"(?:erklär|erklaer|erkläre|erklaere|erzähl|erzaehl)\b|"
    r"(?:ich möchte|ich moechte)\s+(?:lieber|über|ueber)\b|"
    r"(?:hallo|hi|hey|danke|vielen dank|wie|was|warum|wieso)\b)"
)
_TITLE_STOP_WORDS = frozenset({"ja", "nein", "okay", "ok", "danke", "hallo", "hi", "hey", "morgen", "heute", "später", "spaeter"})


@dataclass(frozen=True)
class PendingReminder:
    session_id: str
    original_request: str
    title: str | None
    due_at: str | None
    missing: str
    expires_at: float


@dataclass(frozen=True)
class ReminderResolution:
    reply: str | None = None
    full_request: str | None = None
    intent: ToolCallIntent | None = None


def _verified_due(text: str, *, standalone: bool) -> str | None:
    normalized = re.sub(r"\s+", " ", strip_jarvis_prefix(text).strip())
    if standalone:
        if not _TIME_REPLY_RE.fullmatch(normalized):
            return None
    elif not (_DAY_FRAGMENT.search(normalized) and _CLOCK_FRAGMENT.search(normalized)):
        return None
    # The established legacy parser handles validated dates/weekday rollovers;
    # never inherit its implicit 09:00/default-tomorrow guesses here.
    due_at, _, _ = _extract_due_components(normalized)
    if not due_at:
        return None
    try:
        due = datetime.fromisoformat(due_at)
    except ValueError:
        return None
    now = datetime.now()
    if not now < due <= now + timedelta(days=366):
        return None
    return due.isoformat(timespec="minutes")


def _clean_title(raw: str) -> str | None:
    text = raw.strip().strip(" .,!?:;")
    text = re.sub(r"(?i)^an\s+(?:(?:den|die|das)\s+)?", "", text).strip()
    text = re.sub(r"(?i)^(?:den|die|das)\s+", "", text).strip()
    if not 2 <= len(text) <= 120 or "\n" in text or "\r" in text:
        return None
    if not re.search(r"\w", text) or text.lower() in _TITLE_STOP_WORDS:
        return None
    if re.search(r"(?i)\b(?:https?://|/tool|sudo)\b", text):
        return None
    return text


class ReminderClarifications:
    """Bounded, process-local pending clarification per session.

    Mutations are synchronous between awaits in LegacyRouting. No shared
    global state or DB schema and no tool call can originate from this class.
    """
    def __init__(
        self, *,
        clock: Callable[[], float] = time.monotonic,
        ttl_seconds: float = 120.0,
        max_sessions: int = 32,
    ) -> None:
        self.clock = clock
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self.pending: dict[str, PendingReminder] = {}

    def _prune(self) -> None:
        now = self.clock()
        for session, entry in tuple(self.pending.items()):
            if now >= entry.expires_at:
                self.pending.pop(session, None)

    def has_pending(self, session_id: str) -> bool:
        self._prune()
        return session_id in self.pending

    def clear(self, session_id: str) -> None:
        self.pending.pop(session_id, None)

    def begin(self, session_id: str, message: str, prompt: str) -> bool:
        self._prune()
        text = re.sub(r"\s+", " ", strip_jarvis_prefix(message).strip())
        title: str | None = None
        due_at: str | None = None
        missing = ""
        if prompt == "Wann soll ich dich daran erinnern?":
            match = _REMINDER_WITH_TITLE.fullmatch(text)
            if match:
                title = _clean_title(match.group(1))
                missing = "time" if title else ""
        elif prompt == "Woran soll ich dich erinnern?":
            if re.search(r"(?i)\b(?:erinnerung|reminder)\b", text):
                due_at = _verified_due(text, standalone=False)
                missing = "title" if due_at else ""

        if not missing:
            return False
        self.pending.pop(session_id, None)
        if len(self.pending) >= self.max_sessions:
            oldest = min(self.pending, key=lambda key: self.pending[key].expires_at)
            self.pending.pop(oldest, None)
        self.pending[session_id] = PendingReminder(
            session_id=session_id,
            original_request=message,
            title=title,
            due_at=due_at,
            missing=missing,
            expires_at=self.clock() + self.ttl_seconds,
        )
        return True

    def consume(self, session_id: str, message: str) -> ReminderResolution | None:
        self._prune()
        entry = self.pending.get(session_id)
        if entry is None:
            return None
        answer = re.sub(r"\s+", " ", strip_jarvis_prefix(message).strip())
        if _CANCEL.fullmatch(answer):
            self.clear(session_id)
            return ReminderResolution(reply="Okay, ich habe keine Erinnerung angelegt.")
        if _TOPIC_CHANGE.match(answer) or looks_like_tool_request(answer):
            self.clear(session_id)
            return None

        if entry.missing == "time":
            due_at = _verified_due(answer, standalone=True)
            if not due_at:
                return ReminderResolution(
                    reply="Bitte nenne Datum und Uhrzeit eindeutig, zum Beispiel morgen um 10 Uhr."
                )
            title = entry.title
        else:
            if _DAY_FRAGMENT.search(answer) or _CLOCK_FRAGMENT.search(answer):
                return ReminderResolution(reply="Woran soll ich dich erinnern?")
            title = _clean_title(answer)
            if not title:
                return ReminderResolution(reply="Woran soll ich dich erinnern?")
            due_at = entry.due_at

        if not title or not due_at:
            return ReminderResolution(reply="Bitte formuliere die Erinnerung vollständig.")
        self.clear(session_id)
        # Safety is applied a second time to this fully assembled instruction by
        # LegacyRouting. The existing TurnEngine still owns durable approval.
        full = f"Erinnere mich am {due_at[:10]} um {due_at[11:16]} Uhr an {title}"
        return ReminderResolution(
            full_request=full,
            intent=ToolCallIntent(
                "reminder_create", {"title": title, "due_at": due_at},
                "Vervollstaendigte, explizite Erinnerung nach Rueckfrage",
            ),
        )
