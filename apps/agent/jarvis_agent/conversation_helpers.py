from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .db import normalize_learned_trigger

TOOL_REQUEST_HINTS = (
    "oeffne",
    "öffne",
    "oeffnen",
    "öffnen",
    "open",
    "starte",
    "starten",
    "start",
    "launch",
    "reminder",
    "erinnerung",
    "kalender",
    "calendar",
    "clipboard",
    "zwischenablage",
    "copy",
    "paste",
    "read file",
    "write file",
    "datei",
    "url",
    "browser",
    "raycast",
    "setze",
    "schreibe",
    "fuehre aus",
    "mach",
)

DATE_HINTS = (
    "welches datum",
    "welcher tag",
    "datum",
    "date",
    "heute ist",
)

TIME_HINTS = (
    "wie spaet",
    "wie spät",
    "uhrzeit",
    "wie viel uhr",
    "wieviel uhr",
    "time",
    "aktuelle zeit",
)

READINESS_HINTS = (
    "bist du da",
    "bist du online",
    "bist du bereit",
    "bereit",
    "online",
    "jarvis",
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
    lowered = user_message.strip().lower()
    if not lowered:
        return False
    return any(hint in lowered for hint in TOOL_REQUEST_HINTS)


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
    lowered = normalized.lower()
    if not lowered:
        return None

    if len(lowered) > 90:
        return None

    if looks_like_tool_request(lowered):
        return None

    if re.fullmatch(r"(danke(?: dir)?(?: schoen| schön)?(?: jarvis| sir)?|vielen dank(?:.*)?)", lowered):
        return "Gern, Sir. Soll ich direkt den naechsten Schritt fuer Sie uebernehmen?"

    if re.fullmatch(r"(hallo(?: jarvis)?|hi(?: jarvis)?|hey(?: jarvis)?|guten (?:morgen|tag|abend)(?: jarvis)?)", lowered):
        return "Natuerlich, Sir. Womit kann ich helfen?"

    if re.fullmatch(r"(ok(?:ay)?|passt|perfekt|super|alles klar)", lowered):
        return "Verstanden, Sir."

    if re.search(r"\b(help|hilfe|was kannst du|capabilities|funktionen)\b", lowered):
        return (
            "Ich kann lokal Chat, Notizen, Erinnerungen, Kalender, Kontakte, Mail-Entwuerfe, Nachrichten, Musiksteuerung, "
            "Raycast, App/URL-Start, Zwischenablage sowie sichere Dateiaktionen mit Freigaben ausfuehren. "
            "Zusatz: Ich kann neue Trigger lernen (`/learn`) und Ihre bevorzugten Tools lokal optimieren."
        )

    return None


def quick_system_status_reply(user_message: str, settings: dict[str, Any]) -> str | None:
    normalized = re.sub(r"\s+", " ", user_message.strip())
    lowered = normalized.lower()
    if not lowered:
        return None

    if len(lowered) > 140:
        return None

    status_hints = (
        "status",
        "modell",
        "model",
        "whisper",
        "stt",
        "tts",
        "engine",
        "welches modell",
    )
    if not any(hint in lowered for hint in status_hints):
        return None

    model = str(settings.get("model_name", "-")).strip() or "-"
    whisper_model = Path(str(settings.get("whisper_model_path", "")).strip()).name or "auto"
    tts_engine = str(settings.get("tts_engine", "piper")).strip() or "piper"
    tts_voice = str(settings.get("tts_voice", "")).strip() or "-"

    return (
        f"Systemstatus: Modell {model}, STT {whisper_model}, "
        f"TTS {tts_engine} ({tts_voice}), alles lokal."
    )


def quick_utility_reply(user_message: str) -> str | None:
    normalized = re.sub(r"\s+", " ", user_message.strip())
    lowered = normalized.lower()
    if not lowered:
        return None

    if len(lowered) > 120:
        return None

    if any(hint in lowered for hint in TIME_HINTS):
        now = datetime.now()
        return f"Aktuelle lokale Zeit: {now.strftime('%H:%M')} Uhr."

    if any(hint in lowered for hint in DATE_HINTS) or re.fullmatch(r"(heute\??|welches datum\??)", lowered):
        now = datetime.now()
        weekday = GERMAN_WEEKDAY_BY_INDEX.get(now.weekday(), now.strftime("%A"))
        return f"Heute ist {weekday}, der {now.strftime('%d.%m.%Y')}."

    if re.fullmatch(r"(jarvis\??|bist du da\??|online\??|bereit\??)", lowered) or any(
        hint in lowered for hint in READINESS_HINTS
    ):
        if len(lowered.split()) <= 4:
            return "Ja, Sir. Systeme laufen stabil und ich bin einsatzbereit."

    return None


def quick_clarification_reply(user_message: str) -> str | None:
    normalized = re.sub(r"\s+", " ", user_message.strip())
    lowered = normalized.lower()
    if not lowered:
        return None

    if len(lowered) > 180:
        return None

    has_time_hint = (
        re.search(r"\b\d{1,2}(?::|\.)?\d{0,2}\s*uhr\b", lowered) is not None
        or re.search(r"\b\d{1,2}\.\d{1,2}(?:\.\d{2,4})?\b", lowered) is not None
        or any(word in lowered for word in ("heute", "morgen", "uebermorgen", "übermorgen", *WEEKDAY_HINTS))
    )
    has_quote_content = re.search(r"\"[^\"]+\"|'[^']+'", normalized) is not None
    has_content_hint = has_quote_content or any(
        hint in lowered
        for hint in (
            "dass",
            "lautet",
            "sagt",
            "heisst",
            "heißt",
            "inhalt",
            "text",
            "an ",
            "ans ",
            "daran",
        )
    )

    if any(word in lowered for word in ("erinnerung", "erinner mich", "remind me")):
        if not has_time_hint and not has_content_hint:
            return (
                "Damit ich die Erinnerung sauber anlege, brauche ich Zeitpunkt und Inhalt. "
                "Beispiel: `Jarvis, erinnere mich morgen um 10 Uhr daran, Licht auszumachen.`"
            )
        if not has_time_hint:
            return "Für die Erinnerung fehlt noch der Zeitpunkt. Wann genau soll ich sie setzen, Sir?"
        if not has_content_hint and len(lowered.split()) <= 12:
            return "Für die Erinnerung fehlt noch der genaue Inhalt. Was soll der Reminder sagen, Sir?"

    if any(hint in lowered for hint in CALENDAR_HINTS):
        has_calendar_verb = any(word in lowered for word in ("plane", "plan", "eintragen", "trag", "schedule"))
        if has_calendar_verb and not has_time_hint:
            return "Ich kann den Termin sofort eintragen. Nennen Sie bitte Startzeit und optional Dauer."

    return None
