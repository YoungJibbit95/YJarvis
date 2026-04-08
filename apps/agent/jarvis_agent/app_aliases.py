from __future__ import annotations

import re


APP_ALIAS_MAP: dict[str, str] = {
    "notiz": "Notes",
    "notizen": "Notes",
    "notes": "Notes",
    "kalender": "Calendar",
    "calendar": "Calendar",
    "erinnerung": "Reminders",
    "erinnerungen": "Reminders",
    "reminder": "Reminders",
    "reminders": "Reminders",
    "mail": "Mail",
    "email": "Mail",
    "e-mail": "Mail",
    "nachricht": "Messages",
    "nachrichten": "Messages",
    "message": "Messages",
    "messages": "Messages",
    "musik": "Music",
    "music": "Music",
    "finder": "Finder",
    "safari": "Safari",
    "terminal": "Terminal",
    "raycast": "Raycast",
}


def normalize_app_name(raw_name: str) -> str:
    original = re.sub(r"\s+", " ", str(raw_name or "").strip())
    if not original:
        return ""

    normalized = original.lower()
    normalized = re.sub(r"(?i)^(?:die|den|das)\s+", "", normalized).strip()
    normalized = re.sub(r"(?i)^(?:app)\s+", "", normalized).strip()
    normalized = re.sub(r"(?i)\s+app$", "", normalized).strip()
    normalized = re.sub(r"\s+", " ", normalized).strip()

    if not normalized:
        return ""

    mapped = APP_ALIAS_MAP.get(normalized)
    if mapped:
        return mapped

    # Keep unknown app names usable, but clean up generic wrappers.
    fallback = re.sub(r"(?i)^(?:die|den|das)\s+", "", original).strip()
    fallback = re.sub(r"(?i)^(?:app)\s+", "", fallback).strip()
    fallback = re.sub(r"(?i)\s+app$", "", fallback).strip()
    return re.sub(r"\s+", " ", fallback).strip()

