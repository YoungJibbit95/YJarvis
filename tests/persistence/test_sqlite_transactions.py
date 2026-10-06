"""Real file/connection boundaries: writer contention, WAL and commit failure."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from jarvis_agent.persistence import MigrationError, migrate_database
from jarvis_agent.persistence.registry import BASELINE, Migration
from jarvis_agent.persistence.sql import sql_tokens


def test_two_concurrent_adoptions_record_baseline_once(legacy_db, snapshot):
    before = snapshot(legacy_db)
    ready = Barrier(2)

    def start():
        ready.wait(timeout=10)
        return migrate_database(legacy_db)

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: start(), range(2)))
    assert sorted(results, key=len) == [(), (1,)]
    assert snapshot(legacy_db) == before
    with sqlite3.connect(legacy_db) as connection:
        assert connection.execute("SELECT version FROM schema_migrations").fetchall() == [(1,)]


def test_concurrent_fresh_initialization_is_serialized(tmp_path):
    path = tmp_path / "concurrent.db"
    ready = Barrier(2)

    def start():
        ready.wait(timeout=10)
        return migrate_database(path)

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: start(), range(2)))
    assert sorted(results, key=len) == [(), (1,)]


def test_writer_lock_failure_preserves_data_and_allows_retry(legacy_db, snapshot):
    before = snapshot(legacy_db, include_metadata=True)
    writer = sqlite3.connect(legacy_db, isolation_level=None)
    try:
        writer.execute("BEGIN IMMEDIATE")
        with pytest.raises(MigrationError) as caught:
            migrate_database(legacy_db, timeout=0.01)
        assert isinstance(caught.value.__cause__, sqlite3.OperationalError)
        writer.rollback()
    finally:
        writer.close()
    assert snapshot(legacy_db, include_metadata=True) == before
    assert migrate_database(legacy_db) == (1,)


def test_commit_busy_rolls_back_ddl_and_applied_entry(legacy_db, snapshot):
    before = snapshot(legacy_db, include_metadata=True)
    reader = sqlite3.connect(legacy_db, isolation_level=None)
    try:
        # In DELETE journal mode a reader can prevent COMMIT, not BEGIN IMMEDIATE.
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM sessions").fetchall()
        with pytest.raises(MigrationError) as caught:
            migrate_database(legacy_db, timeout=0.01)
        assert "locked" in str(caught.value.__cause__).lower()
        assert reader.execute("SELECT name FROM sqlite_schema WHERE name='schema_migrations'").fetchall() == []
    finally:
        reader.rollback()
        reader.close()
    assert snapshot(legacy_db, include_metadata=True) == before
    assert migrate_database(legacy_db) == (1,)


def test_live_wal_contents_survive_adoption_with_reader_open(legacy_db, snapshot):
    writer = sqlite3.connect(legacy_db, isolation_level=None)
    reader = sqlite3.connect(legacy_db, isolation_level=None)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT INTO messages VALUES (100, 'legacy-session', 'user', 'WAL-only content', 'original-time')")
        assert legacy_db.with_name(legacy_db.name + "-wal").is_file()
        reader.execute("BEGIN")
        assert reader.execute("SELECT content FROM messages WHERE id=100").fetchone() == ("WAL-only content",)
        before = snapshot(legacy_db)
        assert migrate_database(legacy_db) == (1,)
        assert snapshot(legacy_db) == before
        assert writer.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        # The existing reader retains its original schema snapshot until restart.
        assert reader.execute("SELECT name FROM sqlite_schema WHERE name='schema_migrations'").fetchall() == []
        reader.rollback()
        assert reader.execute("SELECT version FROM schema_migrations").fetchall() == [(1,)]
    finally:
        reader.close()
        writer.close()
    assert migrate_database(legacy_db) == ()


def test_wal_failed_migration_preserves_existing_fts_and_rows(legacy_db, snapshot):
    keeper = sqlite3.connect(legacy_db, isolation_level=None)
    try:
        keeper.execute("PRAGMA journal_mode=WAL")
        before = snapshot(legacy_db, include_metadata=True)
        failing = Migration(2, (
            "CREATE TABLE rollback_probe (id INTEGER)",
            "UPDATE memory_items SET content='temporary replacement' WHERE id=41",
            "INSERT INTO missing_table VALUES(1)",
        ))
        with pytest.raises(MigrationError):
            migrate_database(legacy_db, (BASELINE, failing))
        assert snapshot(legacy_db, include_metadata=True) == before
        assert keeper.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    finally:
        keeper.close()


def test_sql_signature_ignores_formatting_not_literal_changes(legacy_statements, tmp_path, make_legacy):
    formatted = tuple("/* same definition */\n" + sql.replace("CREATE TABLE", "create   table") for sql in legacy_statements)
    path = make_legacy(tmp_path / "formatted.db", statements=formatted)
    assert migrate_database(path) == (1,)
    assert sql_tokens("SELECT 'two  spaces'") != sql_tokens("SELECT 'two spaces'")
    assert sql_tokens("SELECT 'UPPER'") != sql_tokens("SELECT 'upper'")
    assert sql_tokens("SELECT '/* literal */'") == ("select", "'/* literal */'")


def test_non_sql_exception_rolls_back_new_metadata(legacy_db, snapshot, monkeypatch):
    from jarvis_agent.persistence import runner

    before = snapshot(legacy_db, include_metadata=True)
    original = runner._record

    def interrupted_record(connection, version):
        original(connection, version)
        raise KeyboardInterrupt("simulated interruption before commit")

    monkeypatch.setattr(runner, "_record", interrupted_record)
    with pytest.raises(KeyboardInterrupt):
        migrate_database(legacy_db)
    assert snapshot(legacy_db, include_metadata=True) == before
