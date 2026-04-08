import os
import time
from pathlib import Path

from jarvis_agent.audio import _cleanup_temp_directory, _parse_say_voices, normalize_transcript_text


def _touch_with_mtime(path: Path, mtime: float) -> None:
    path.write_text("x", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_normalize_wake_word_with_prefix():
    text = normalize_transcript_text("hey jobs, mach das licht an")
    assert text == "hey Jarvis, mach das licht an"


def test_normalize_wake_word_at_start_with_command_hint():
    text = normalize_transcript_text("jobs starte einen timer auf 5 minuten")
    assert text == "Jarvis starte einen timer auf 5 minuten"


def test_normalize_exact_alias_to_wake_word():
    text = normalize_transcript_text("jobs")
    assert text == "Jarvis"


def test_normalize_common_stt_mishear_thanks_phrase():
    text = normalize_transcript_text("Don get your job is.")
    assert text == "danke dir Jarvis"


def test_does_not_overwrite_regular_jobs_usage():
    text = normalize_transcript_text("ich habe drei jobs im backlog")
    assert text == "ich habe drei jobs im backlog"


def test_normalize_bavarian_command_variants():
    text = normalize_transcript_text("jarvis i moechte ned dass du des loeschst")
    assert text == "jarvis ich moechte nicht dass du das loeschst"


def test_filter_short_station_year_hallucination():
    text = normalize_transcript_text("swr 2020")
    assert text == ""


def test_cleanup_temp_directory_keeps_newest_entries(tmp_path: Path):
    now = time.time()
    old_file = tmp_path / "old.wav"
    mid_file = tmp_path / "mid.wav"
    new_file = tmp_path / "new.wav"

    _touch_with_mtime(old_file, now - 300)
    _touch_with_mtime(mid_file, now - 200)
    _touch_with_mtime(new_file, now - 100)

    _cleanup_temp_directory(tmp_path, keep_entries=2, max_age_seconds=10_000)

    assert not old_file.exists()
    assert mid_file.exists()
    assert new_file.exists()


def test_cleanup_temp_directory_removes_old_by_age(tmp_path: Path):
    now = time.time()
    stale = tmp_path / "stale.wav"
    fresh = tmp_path / "fresh.wav"

    _touch_with_mtime(stale, now - 20_000)
    _touch_with_mtime(fresh, now - 60)

    _cleanup_temp_directory(tmp_path, keep_entries=5, max_age_seconds=3_600)

    assert not stale.exists()
    assert fresh.exists()


def test_parse_say_voices_extracts_voice_names():
    raw = """
Anna                de_DE    # Hallo! Ich heiße Anna.
Eddy (Deutsch (Deutschland)) de_DE    # Hallo! Ich heiße Eddy.
"""
    voices = _parse_say_voices(raw)
    assert voices == ["Anna", "Eddy (Deutsch (Deutschland))"]
