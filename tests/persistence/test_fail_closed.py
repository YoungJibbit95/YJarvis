import sqlite3

import pytest

from jarvis_agent.persistence import MigrationError, migrate_database
from jarvis_agent.persistence.schema import METADATA_SQL


@pytest.mark.parametrize("missing", ["sessions", "tool_learning_stats", "memory_items_fts", "memory_items_ai", "memory_items_ad", "memory_items_au"])
def test_partial_schema_is_not_adopted(tmp_path, make_legacy, legacy_statements, missing):
    # Omit a historical CREATE statement; never repair or delete a user's table.
    statements = [sql for sql in legacy_statements if f"IF NOT EXISTS {missing} " not in sql and f"IF NOT EXISTS {missing}\n" not in sql]
    path = make_legacy(tmp_path / "partial.db", statements=statements, populate=False)
    original = path.read_bytes()
    with pytest.raises(MigrationError, match="inconsistent schema") as caught:
        migrate_database(path)
    assert "preserve the database" in str(caught.value)
    assert path.read_bytes() == original
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM sqlite_schema WHERE name='schema_migrations'").fetchall() == []


@pytest.mark.parametrize("before,after", [
    ("importance REAL NOT NULL DEFAULT 0.5", "importance REAL NOT NULL DEFAULT 0.25"),
    ("ON DELETE CASCADE", "ON DELETE RESTRICT"),
    ("content='memory_items'", "content='messages'"),
    ("VALUES (new.id, new.content);", "VALUES (new.id, 'changed  text');"),
    ("enabled INTEGER NOT NULL DEFAULT 1", "enabled INTEGER NOT NULL DEFAULT 0"),
    ("path TEXT PRIMARY KEY", "path BLOB PRIMARY KEY"),
])
def test_same_names_with_wrong_definitions_are_rejected(tmp_path, make_legacy, legacy_statements, before, after):
    statements = tuple(sql.replace(before, after) for sql in legacy_statements)
    assert statements != legacy_statements
    path = make_legacy(tmp_path / "wrong.db", statements=statements, populate=False)
    original = path.read_bytes()
    with pytest.raises(MigrationError, match="inconsistent schema"):
        migrate_database(path)
    assert path.read_bytes() == original


@pytest.mark.parametrize("extra", ["CREATE TABLE unrelated(id INTEGER)", "CREATE INDEX extra_idx ON settings(value)", "CREATE VIEW extra_view AS SELECT * FROM settings"])
def test_unknown_objects_are_not_silently_accepted(legacy_db, extra, snapshot):
    with sqlite3.connect(legacy_db) as connection:
        connection.execute(extra)
    original = legacy_db.read_bytes()
    before = snapshot(legacy_db)
    with pytest.raises(MigrationError, match="inconsistent schema"):
        migrate_database(legacy_db)
    assert legacy_db.read_bytes() == original
    assert snapshot(legacy_db) == before


def test_orphaned_foreign_key_is_not_repaired(legacy_db, snapshot):
    with sqlite3.connect(legacy_db) as connection:
        connection.execute("INSERT INTO messages VALUES (99, 'missing-session', 'user', 'preserve orphan', 'old')")
    before = snapshot(legacy_db)
    original = legacy_db.read_bytes()
    with pytest.raises(MigrationError, match="foreign-key violations"):
        migrate_database(legacy_db)
    assert snapshot(legacy_db) == before
    assert legacy_db.read_bytes() == original


def test_stale_external_content_fts_index_is_not_rebuilt(tmp_path, make_legacy, legacy_statements, snapshot):
    triggers = [sql for sql in legacy_statements if "CREATE TRIGGER" in sql]
    without = [sql for sql in legacy_statements if "CREATE TRIGGER" not in sql]
    path = make_legacy(tmp_path / "stale-fts.db", statements=without)
    with sqlite3.connect(path) as connection:
        for sql in triggers:
            connection.execute(sql)
        assert connection.execute("SELECT rowid FROM memory_items_fts WHERE memory_items_fts MATCH 'Atlas'").fetchall() == []
    before = snapshot(path)
    original = path.read_bytes()
    with pytest.raises(MigrationError):
        migrate_database(path)
    assert snapshot(path) == before
    assert path.read_bytes() == original


@pytest.mark.parametrize("pragma", ["user_version", "application_id"])
def test_unrecognized_header_values_fail_closed(legacy_db, pragma):
    with sqlite3.connect(legacy_db) as connection:
        connection.execute(f"PRAGMA {pragma}=42")
    original = legacy_db.read_bytes()
    with pytest.raises(MigrationError, match="header"):
        migrate_database(legacy_db)
    assert legacy_db.read_bytes() == original


def test_non_sqlite_file_is_never_replaced(tmp_path):
    path = tmp_path / "valuable.db"
    path.write_bytes(b"This is not SQLite. Preserve these bytes.")
    with pytest.raises(MigrationError):
        migrate_database(path)
    assert path.read_bytes() == b"This is not SQLite. Preserve these bytes."


@pytest.mark.parametrize("metadata", [
    "CREATE TABLE schema_migrations(version TEXT, applied_at TEXT)",
    "CREATE TABLE schema_migrations(version INTEGER, applied_at TEXT)",
    "CREATE VIEW schema_migrations AS SELECT 1 AS version, 'now' AS applied_at",
])
def test_malformed_ledger_is_rejected(legacy_db, metadata):
    with sqlite3.connect(legacy_db) as connection:
        connection.execute(metadata)
    original = legacy_db.read_bytes()
    with pytest.raises(MigrationError):
        migrate_database(legacy_db)
    assert legacy_db.read_bytes() == original


@pytest.mark.parametrize("rows", [[], [(2, "2026-10-06T17:00:00Z")], [(1, "invalid")], [(1, "2026-10-06T17:00:00")]])
def test_bad_ledger_history_is_not_assumed_to_be_fresh(legacy_db, rows):
    with sqlite3.connect(legacy_db) as connection:
        connection.execute(METADATA_SQL)
        connection.executemany("INSERT INTO schema_migrations VALUES (?, ?)", rows)
    original = legacy_db.read_bytes()
    with pytest.raises(MigrationError):
        migrate_database(legacy_db)
    assert legacy_db.read_bytes() == original


def test_ledger_without_runtime_schema_is_not_valid(tmp_path):
    path = tmp_path / "metadata-only.db"
    with sqlite3.connect(path) as connection:
        connection.execute(METADATA_SQL)
        connection.execute("INSERT INTO schema_migrations VALUES (1, '2026-10-06T17:00:00Z')")
    original = path.read_bytes()
    with pytest.raises(MigrationError, match="inconsistent schema"):
        migrate_database(path)
    assert path.read_bytes() == original


def test_already_migrated_schema_drift_is_not_ignored(legacy_db):
    migrate_database(legacy_db)
    with sqlite3.connect(legacy_db) as connection:
        connection.execute("ALTER TABLE settings ADD COLUMN unknown_column TEXT")
    original = legacy_db.read_bytes()
    with pytest.raises(MigrationError, match="inconsistent schema"):
        migrate_database(legacy_db)
    assert legacy_db.read_bytes() == original


def test_internal_only_database_is_not_silently_classified_as_fresh(tmp_path):
    path = tmp_path / "internal-only.db"
    with sqlite3.connect(path) as connection:
        connection.execute("ANALYZE")
        assert connection.execute("SELECT name FROM sqlite_schema").fetchall() == [("sqlite_stat1",)]
    before = path.read_bytes()
    with pytest.raises(MigrationError, match="Internal-only schema"):
        migrate_database(path)
    assert path.read_bytes() == before
