from pathlib import Path

from jarvis_agent.profile import DEFAULT_PROFILE
from jarvis_agent.safety import (
    confirmation_message,
    detect_blocked_user_request,
    detect_confirmation_required_request,
    detect_dangerous_content,
    is_confirmation_message,
    is_critical_path,
)


def test_blocks_destructive_user_request():
    reason = detect_blocked_user_request("Bitte loesch das gesamte System jetzt", DEFAULT_PROFILE)
    assert reason is not None


def test_blocks_generic_destructive_phrase():
    reason = detect_blocked_user_request("Bitte wipe den kompletten Mac und alle Daten", DEFAULT_PROFILE)
    assert reason is not None


def test_detects_dangerous_script_content():
    pattern = detect_dangerous_content("#!/bin/bash\nrm -rf /", DEFAULT_PROFILE)
    assert pattern == "rm -rf /"


def test_blocks_critical_path():
    assert is_critical_path(Path("/System/Library/test.txt"), DEFAULT_PROFILE)


def test_non_critical_path_is_not_blocked():
    safe_path = Path.home() / "Documents" / "jarvis-safe.txt"
    assert not is_critical_path(safe_path, DEFAULT_PROFILE)


def test_confirmation_required_for_sensitive_request():
    reason = detect_confirmation_required_request(
        "Bitte fuehre das mit sudo aus und setze einen LaunchDaemon auf.",
        DEFAULT_PROFILE,
    )
    assert reason is not None


def test_confirmation_phrase_recognized():
    assert is_confirmation_message("Bestaetige", DEFAULT_PROFILE)
    assert is_confirmation_message("Ich bestaetige den Auftrag", DEFAULT_PROFILE)


def test_confirmation_message_contains_instruction():
    text = confirmation_message(DEFAULT_PROFILE, reason="sudo ")
    assert "Bestaetige" in text
