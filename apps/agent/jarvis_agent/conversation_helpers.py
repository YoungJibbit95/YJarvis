from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .db import normalize_learned_trigger

# Recognize action verbs with word boundaries, not arbitrary substrings.
TOOL_ACTION_RE = re.compile(
    r"(?i)\b(?:oeffne|öffne|oeffnen|öffnen|open|starte|starten|start|launch|"
    r"kopiere|kopier|paste|setze|schreibe|schreib|fuehre|führe|"
    r"erinner(?:e)?\s+mich|remind\s+me|"
    r"zeige|suche|finde|liste|plane|trag(?:e)?|pausiere|pausieren|"
    r"sende|schicke|notiere|erstell(?:e)?|loesch(?:e)?|lösche|"
    r"lies|lese|read|write)\b"
)
META_DISCUSSION_RE = re.compile(
    r"(?i)^(?:ich (?:möchte|moechte|will|würde gern|wuerde gern)\s+"
    r"(?:über|ueber)\b|"
    r"(?:wie|warum|wieso|weshalb|was|welche|welcher)\b|"
    r"(?:erklär|erkläre|erklaere|erzähl|erzaehl|beschreib)\b|"
    r"kannst du (?:mir )?(?:erklären|erklaeren|erzählen|erzaehlen)\b)"
)
SHORT_FOLLOWUP_RE = re.compile(
    r"(?i)^(?:mach|mache)\s+(?:es|das|die antwort)\s+"
    r"(?:kürzer|kuerzer|einfacher|genauer|verständlicher|verstaendlicher)\b"
)

WEEKDAY_HINTS = (
    "montag",
    "dienstag",
    "mittwoch",
    "donnerstag",
    "freitag",
    "samstag",
    "sonntag",
)

CALENDAR_HINTS = (
    "kalender",
    "termin",
    "event",
    "eintrag",
)

LEARN_LIST_HINTS = (
    "/learn-list",
    "/lernen-liste",
    "zeige gelernte befehle",
    "zeige gelernte funktionen",
    "welche befehle hast du gelernt",
)

GERMAN_WEEKDAY_BY_INDEX = {
    0: "Montag",
    1: "Dienstag",
    2: "Mittwoch",
    3: "Donnerstag",
    4: "Freitag",
    5: "Samstag",
    6: "Sonntag",
}


def looks_like_tool_request(user_message: str) -> bool:
    message = strip_jarvis_prefix(user_message).strip().lower()
    message = re.sub(r"(?i)^bitte[\s,]+", "", message)
    if not message:
        return False
    if message.startswith("/tool "):
        return True
    if SHORT_FOLLOWUP_RE.match(message) or META_DISCUSSION_RE.match(message):
        return False
    # Keep an ambiguous "mach xyz" in the clarification path, never execute it.
    if re.match(r"^(?:mach|mache)\s+", message):
        return True
    if re.search(r"\b(?:datei|file)\s+(?:lesen|schreiben|read|write)\b", message):
        return True
    if re.search(r"\b(?:musik|music)\s+(?:pausieren|pause|weiter|stoppen)\b", message):
        return True
    return TOOL_ACTION_RE.search(message) is not None


def normalize_honorifics(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        return normalized

    normalized = re.sub(r"\bmein(?:e|er)?\s+herr(?:n)?\b", "Sir", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bmein(?:e|er)?\s+gebiete?r\b", "Sir", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def strip_jarvis_prefix(text: str) -> str:
    return re.sub(r"(?i)^\s*jarvis[\s,:;\-]*", "", text.strip()).strip()


def _strip_wrapping_quotes(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1].strip()
    return stripped


def _normalize_learn_trigger_text(raw: str) -> str:
    cleaned = _strip_wrapping_quotes(raw)
    cleaned = re.sub(r"(?i)\b(?:ich|sage|sag|schreibe|tippe|eingebe|den befehl|das kommando)\b", " ", cleaned)
    cleaned = _strip_wrapping_quotes(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.:;!?-")
    return normalize_learned_trigger(cleaned)


def is_learn_list_request(user_message: str) -> bool:
    lowered = strip_jarvis_prefix(user_message).lower().strip()
    if not lowered:
        return False
    return any(hint in lowered for hint in LEARN_LIST_HINTS)


def parse_learn_definition_request(user_message: str) -> tuple[str, str] | None:
    message = strip_jarvis_prefix(user_message).strip()
    if not message:
        return None

    slash_patterns = (
        r'(?is)^/learn\s+"([^"]+)"\s*(?:=>|->)\s*(.+)$',
        r"(?is)^/learn\s+'([^']+)'\s*(?:=>|->)\s*(.+)$",
        r'(?is)^/learn\s+"([^"]+)"\s+(.+)$',
        r"(?is)^/learn\s+'([^']+)'\s+(.+)$",
        r"(?is)^/learn\s+(.+?)\s*(?:=>|->)\s*(.+)$",
    )
    for pattern in slash_patterns:
        match = re.match(pattern, message)
        if not match:
            continue
        trigger = _normalize_learn_trigger_text(match.group(1))
        action_text = match.group(2).strip()
        action_text = strip_jarvis_prefix(action_text)
        action_text = re.sub(r"\s+", " ", action_text).strip()
        if trigger and action_text:
            return trigger, action_text
        return None

    natural_match = re.search(
        r"(?is)\b(?:lern(?:e)?|teach)\b.*?\bwenn ich\b\s+(.+?)\s+\bdann\b\s+(.+)$",
        message,
    )
    if not natural_match:
        return None

    trigger = _normalize_learn_trigger_text(natural_match.group(1))
    action_text = natural_match.group(2).strip()
    action_text = strip_jarvis_prefix(action_text)
    action_text = re.sub(r"\s+", " ", action_text).strip()
    action_text = action_text.rstrip(" .")
    if not trigger or not action_text:
        return None
    return trigger, action_text


def parse_unlearn_request(user_message: str) -> str | None:
    message = strip_jarvis_prefix(user_message).strip()
    if not message:
        return None

    patterns = (
        r'(?is)^/unlearn\s+"([^"]+)"\s*$',
        r"(?is)^/unlearn\s+'([^']+)'\s*$",
        r"(?is)^/unlearn\s+(.+)$",
        r'(?is)^(?:vergiss|loesch(?:e)?|entfern(?:e)?)\s+(?:den\s+)?(?:befehl|kommando|trigger)\s+"([^"]+)"\s*$',
        r"(?is)^(?:vergiss|loesch(?:e)?|entfern(?:e)?)\s+(?:den\s+)?(?:befehl|kommando|trigger)\s+(.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, message)
        if not match:
            continue
        trigger = _normalize_learn_trigger_text(match.group(1))
        if trigger:
            return trigger
    return None


def tool_performance_score(stats: dict[str, Any] | None) -> float:
    if not stats:
        return 0.0

    success_count = int(stats.get("success_count", 0))
    failure_count = int(stats.get("failure_count", 0))
    total = success_count + failure_count
    if total <= 0:
        return 0.0

    success_rate = (success_count + 1.0) / float(total + 2)
    average_latency = float(stats.get("average_latency_ms", 0.0) or 0.0)
    speed_component = 1.0 / (1.0 + (max(0.0, average_latency) / 1800.0))
    confidence_component = min(1.0, total / 20.0)

    return (success_rate * 0.65) + (speed_component * 0.25) + (confidence_component * 0.10)


def quick_local_reply(user_message: str) -> str | None:
    normalized = re.sub(r"\s+", " ", user_message.strip())
    lowered = strip_jarvis_prefix(normalized).lower().strip(" \t.,!?;:")
    if not lowered or len(lowered) > 90 or looks_like_tool_request(lowered):
        return None

    if re.fullmatch(
        r"(?:danke(?: dir)?(?: schoen| schön)?(?:,?\s*(?:jarvis|sir))?|"
        r"vielen dank(?:,?\s*(?:jarvis|sir))?)", lowered
    ):
        return "Gerne."
    if re.fullmatch(
        r"(?:hallo|hi|hey|guten (?:morgen|tag|abend))(?:,?\s*jarvis)?", lowered
    ):
        return "Hallo! Wie kann ich helfen?"
    if re.fullmatch(r"(?:ok(?:ay)?|passt|perfekt|super|alles klar)", lowered):
        return "Alles klar."
    if re.fullmatch(
        r"(?:help|hilfe|was kannst du(?: alles)?|"
        r"welche (?:funktionen|faehigkeiten|fähigkeiten) hast du)", lowered
    ):
        return (
            "Ich kann lokal Chat, Notizen, Erinnerungen, Kalender, Kontakte, Mail-Entwuerfe, Nachrichten, Musiksteuerung, "
            "Raycast, App/URL-Start, Zwischenablage sowie sichere Dateiaktionen mit Freigaben ausfuehren. "
            "Zusatz: Ich kann neue Trigger lernen (/learn) und bevorzugte Tools lokal optimieren."
        )
    return None


def quick_system_status_reply(user_message: str, settings: dict[str, Any]) -> str | None:
    normalized = re.sub(r"\s+", " ", strip_jarvis_prefix(user_message).strip())
    lowered = normalized.lower()
    if not lowered or len(lowered) > 140 or looks_like_tool_request(lowered):
        return None
    if not (
        re.search(r"\b(?:systemstatus|status|systemübersicht|systemuebersicht)\b", lowered)
        or re.search(r"\b(?:welches modell|welchen (?:whisper|stt|tts)|welche (?:stimme|engine))\b", lowered)
        or re.search(r"\b(?:modell|whisper|stt|tts)\b.*\b(?:nutzt|benutzt|verwendest|konfiguriert)\b", lowered)
    ):
        return None

    model = str(settings.get("model_name", "-")).strip() or "-"
    whisper_model = Path(str(settings.get("whisper_model_path", "")).strip()).name or "auto"
    tts_engine = str(settings.get("tts_engine", "piper")).strip() or "piper"
    tts_voice = str(settings.get("tts_voice", "")).strip() or "-"
    # Configuration does not establish live process, model or device health.
    return (
        f"Konfiguriert: Modell {model}, STT {whisper_model}, "
        f"TTS {tts_engine} ({tts_voice}). Das ist keine Live-Systemprüfung."
    )


def quick_utility_reply(user_message: str) -> str | None:
    original = user_message.strip().lower().strip(" \t.,!?;:")
    normalized = re.sub(r"\s+", " ", strip_jarvis_prefix(user_message).strip())
    lowered = normalized.lower().strip(" \t.,!?;:")
    lowered = re.sub(r"^bitte[\s,]+", "", lowered)
    if len(lowered) > 120:
        return None

    time_questions = (
        r"(?:wie (?:spät|spaet) (?:ist es|haben wir es)(?: gerade| jetzt)?|"
        r"wie (?:viel|viele) uhr (?:ist es|haben wir)(?: gerade| jetzt)?|"
        r"(?:was ist |sag(?:e)? mir )?(?:die |unsere )?(?:aktuelle )?uhrzeit|"
        r"welche uhrzeit (?:ist es|haben wir))"
    )
    date_questions = (
        r"(?:welches datum (?:haben wir|ist heute|ist es)?|"
        r"welcher tag (?:ist heute|ist es heute)|"
        r"was (?:ist heute|haben wir heute) (?:für|fuer) (?:ein|einen) (?:datum|tag)|"
        r"heute)"
    )
    if re.fullmatch(time_questions, lowered):
        now = datetime.now()
        return f"Aktuelle lokale Zeit: {now.strftime('%H:%M')} Uhr."
    if re.fullmatch(date_questions, lowered):
        now = datetime.now()
        weekday = GERMAN_WEEKDAY_BY_INDEX.get(now.weekday(), now.strftime("%A"))
        return f"Heute ist {weekday}, der {now.strftime('%d.%m.%Y')}."
    if original == "jarvis" or re.fullmatch(
        r"(?:bist du (?:da|online|bereit)|(?:bist )?bereit|online)", lowered
    ):
        return "Ja, ich bin da."
    return None


def quick_clarification_reply(user_message: str) -> str | None:
    normalized = re.sub(r"\s+", " ", strip_jarvis_prefix(user_message).strip())
    lowered = normalized.lower()
    if not lowered or len(lowered) > 180:
        return None

    if re.fullmatch(r"(?:lies|lese)\s+(?:diese|die)\s+datei[.!?]?", lowered):
        return "Welche Datei soll ich lesen?"

    # A question *about* reminders is not an instruction to create one.
    if not looks_like_tool_request(lowered):
        return None
    if re.search(
        r"\b(?:zeige|liste|suche|finde|offene)\s+(?:mir\s+)?erinnerungen\b", lowered
    ):
        return None

    reminder_action = re.search(
        r"\b(?:erinner(?:e)?\s+mich|remind me)\b", lowered
    ) or (
        re.search(r"\b(?:erinnerung|reminder)\b", lowered)
        and re.search(r"\b(?:mach|erstell(?:e)?|setze|lege)\b", lowered)
    )
    if reminder_action:
        has_time = (
            re.search(r"\b\d{1,2}(?::|\.)?\d{0,2}\s*uhr\b", lowered) is not None
            or re.search(r"\b\d{1,2}\.\d{1,2}(?:\.\d{2,4})?\b", lowered) is not None
            or re.search(
                r"\b(?:heute|morgen|uebermorgen|übermorgen|"
                + "|".join(WEEKDAY_HINTS) + r")\b", lowered
            ) is not None
        )
        has_content = (
            re.search(r"\"[^\"]+\"|'[^']+'", normalized) is not None
            or re.search(
                r"\b(?:an|ans|daran|dass|lautet|sagt|inhalt|text)\b", lowered
            ) is not None
        )
        if not has_content:
            return "Was soll in der Erinnerung stehen?" if not has_time else "Woran soll ich dich erinnern?"
        if not has_time:
            return "Wann soll ich dich daran erinnern?"

    if re.search(r"\b(?:plane|plan|trag|eintragen|schedule)\b", lowered) and re.search(
        r"\b(?:kalender|termin|event|eintrag)\b", lowered
    ):
        has_time = re.search(
            r"\b(?:heute|morgen|uebermorgen|übermorgen|"
            + "|".join(WEEKDAY_HINTS) + r"|\d{1,2}\s*uhr)\b", lowered
        )
        if not has_time:
            return "Wann soll der Termin beginnen?"

    return None
