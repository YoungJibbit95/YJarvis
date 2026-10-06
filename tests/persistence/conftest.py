"""Historical fixtures use frozen V1 SQL, never the new baseline implementation."""

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def legacy_statements():
    source = (Path(__file__).resolve().parents[1] / "fixtures" / "legacy_v1_schema.sql").read_text()
    statements = []
    pending = ""
    for char in source:
        pending += char
        if char == ";" and sqlite3.complete_statement(pending):
            statements.append(pending.strip())
            pending = ""
    assert not pending.strip()
    assert len(statements) == 14
    return tuple(statements)


@pytest.fixture
def make_legacy(legacy_statements):
    def create(path, *, statements=None, populate=True):
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            for statement in legacy_statements if statements is None else statements:
                connection.execute(statement)
            if populate:
                connection.execute("INSERT INTO sessions VALUES ('legacy-session', '2020-01-02T03:04:05Z')")
                connection.executemany(
                    "INSERT INTO messages VALUES (?, 'legacy-session', ?, ?, '2020-01-02T03:04:06Z')",
                    [(17, "user", "  Nicht umschreiben: Grüße!  "), (18, "assistant", "Bestätigt.")],
                )
                connection.execute(
                    "INSERT INTO tool_runs VALUES ('legacy-tool', 'legacy-session', 'legacy-run', "
                    "'open_app', '{\"app\": \"Safari\"}', NULL, 'original error', 0, '2020-01-02T03:04:07Z')"
                )
                connection.execute(
                    "INSERT INTO approvals VALUES ('legacy-approval', 'legacy-session', 'legacy-run', "
                    "'open_app', '{\"app\": \"Safari\"}', 'pending', NULL, '2020-01-02T03:04:08Z', NULL)"
                )
                connection.executemany(
                    "INSERT INTO memory_items VALUES (?, ?, ?, ?, '2020-01-02T03:04:09Z')",
                    [(41, "legacy-session", "Projekt Atlas Erinnerung", 0.875),
                     (49, None, "Dauerhafte Notiz", 0.25)],
                )
                settings = {
                    "model_name": "custom-local-model", "language": "de-CH",
                    "ollama_base_url": "http://127.0.0.1:11434", "tts_engine": "say",
                    "tts_model_path": "/preserve/model.onnx", "tts_voice": "custom-voice",
                    "say_rate_wpm": "219", "tts_sir_pronunciation": "Sir",
                    "whisper_model_path": "/preserve/whisper.bin", "whisper_binary": "custom-whisper",
                    "custom-setting": "  preserve whitespace  ",
                }
                connection.executemany("INSERT INTO settings VALUES (?, ?)", settings.items())
                connection.executemany("INSERT INTO allowed_paths VALUES (?)", [(str(path.parent),), ("/preserve/allowed",)])
                connection.execute(
                    "INSERT INTO smarthome_entities VALUES ('light.custom', 'light', 'Eigenes Licht', "
                    "'on', '{\"brightness\": 73}')"
                )
                connection.execute(
                    "INSERT INTO learned_commands VALUES ('fokus', 'open_app', '{\"app\": \"Safari\"}', "
                    "'2020-01-02T03:04:10Z', '2020-01-03T03:04:10Z', 1, 9, 7, 2)"
                )
                connection.execute(
                    "INSERT INTO tool_learning_stats VALUES ('open_app', 7, 2, 12.75, 18, '2020-01-03T03:04:10Z')"
                )
            connection.commit()
        finally:
            connection.close()
        return path
    return create


@pytest.fixture
def legacy_db(tmp_path, make_legacy):
    return make_legacy(tmp_path / "legacy.db")


@pytest.fixture
def snapshot():
    def capture(path, *, include_metadata=False):
        connection = sqlite3.connect(path)
        try:
            tables = [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
            ) if include_metadata or row[0] != "schema_migrations"]
            # Include FTS shadow rows and sqlite_sequence, not just app-level DTOs.
            return {table: sorted(connection.execute(
                'SELECT * FROM "' + table.replace('"', '""') + '"'
            ).fetchall(), key=repr) for table in tables}
        finally:
            connection.close()
    return capture
