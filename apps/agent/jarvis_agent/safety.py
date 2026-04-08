from __future__ import annotations

from pathlib import Path
from typing import Any


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _safety_config(profile: dict[str, Any]) -> dict[str, Any]:
    safety = profile.get("safety", {})
    if not isinstance(safety, dict):
        return {}
    return safety


def _resolve_path(raw_path: str) -> Path:
    return Path(raw_path).expanduser().resolve()


def detect_blocked_user_request(user_message: str, profile: dict[str, Any]) -> str | None:
    lowered = user_message.lower()
    safety = _safety_config(profile)
    patterns = _as_list(safety.get("blocked_request_patterns"))

    for pattern in patterns:
        if pattern.lower() in lowered:
            return pattern

    destructive_verbs = [
        "loesch",
        "delete",
        "wipe",
        "erase",
        "format",
        "destroy",
        "vernichte",
        "zerstoere",
        "rm -rf",
    ]
    critical_targets = [
        "system",
        "pc",
        "mac",
        "festplatte",
        "disk",
        "daten",
        "all data",
        "/",
        "root",
        "os",
    ]

    if any(verb in lowered for verb in destructive_verbs) and any(
        target in lowered for target in critical_targets
    ):
        return "generische destruktive Anfrage"

    return None


def detect_confirmation_required_request(
    user_message: str,
    profile: dict[str, Any],
) -> str | None:
    lowered = user_message.lower()
    safety = _safety_config(profile)
    patterns = _as_list(safety.get("confirmation_required_patterns"))

    for pattern in patterns:
        if pattern.lower() in lowered:
            return pattern
    return None


def is_confirmation_message(user_message: str, profile: dict[str, Any]) -> bool:
    normalized = user_message.strip().lower()
    safety = _safety_config(profile)

    explicit_phrases = _as_list(safety.get("confirmation_accept_phrases"))
    for phrase in explicit_phrases:
        if normalized == phrase.lower():
            return True

    default_prefixes = [
        "bestaetige",
        "ich bestaetige",
        "confirm",
        "yes confirm",
    ]
    prefixes = _as_list(safety.get("confirmation_accept_prefixes"))
    if not prefixes:
        prefixes = default_prefixes
    else:
        prefixes = prefixes + [item for item in default_prefixes if item not in prefixes]

    for prefix in prefixes:
        if normalized.startswith(prefix.lower()):
            return True

    return False


def is_critical_path(target: Path, profile: dict[str, Any]) -> bool:
    safety = _safety_config(profile)
    prefixes = _as_list(safety.get("blocked_path_prefixes"))

    resolved_target = _resolve_path(str(target))

    for prefix in prefixes:
        try:
            critical_root = _resolve_path(prefix)
        except Exception:
            continue

        if resolved_target == critical_root or critical_root in resolved_target.parents:
            return True

    return False


def detect_dangerous_content(content: str, profile: dict[str, Any]) -> str | None:
    lowered = content.lower()
    safety = _safety_config(profile)
    patterns = _as_list(safety.get("blocked_content_patterns"))

    for pattern in patterns:
        if pattern.lower() in lowered:
            return pattern
    return None


def refusal_message(profile: dict[str, Any], *, reason: str | None = None) -> str:
    safety = _safety_config(profile)
    base_message = str(
        safety.get(
            "refusal_message",
            "Diese Anfrage ist aus Sicherheitsgruenden blockiert.",
        )
    ).strip()

    if reason:
        return f"{base_message} Grund: {reason}."

    return base_message


def confirmation_message(profile: dict[str, Any], *, reason: str | None = None) -> str:
    safety = _safety_config(profile)
    base_message = str(
        safety.get(
            "confirmation_required_message",
            "Diese Anfrage ist kritisch. Bitte bestaetige explizit, bevor ich fortfahre.",
        )
    ).strip()

    instruction = str(
        safety.get(
            "confirmation_instruction",
            "Antworte mit `Bestaetige`, wenn ich den Auftrag ausfuehren soll.",
        )
    ).strip()

    if reason:
        return f"{base_message} Grund: {reason}. {instruction}"

    return f"{base_message} {instruction}"
