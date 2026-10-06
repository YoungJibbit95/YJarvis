import sqlite3

import pytest

from jarvis_agent.persistence import MigrationError, migrate_database
from jarvis_agent.persistence.registry import BASELINE, Migration


SECOND = Migration(2, (
    "CREATE TABLE migration_probe (position INTEGER PRIMARY KEY, value TEXT NOT NULL)",
    "INSERT INTO migration_probe VALUES (1, 'second')",
))
THIRD = Migration(3, ("INSERT INTO migration_probe VALUES (2, 'third')",))


def test_versions_are_sorted_and_each_runs_once(legacy_db, snapshot):
    registry = (THIRD, BASELINE, SECOND)
    assert migrate_database(legacy_db, registry) == (1, 2, 3)
    with sqlite3.connect(legacy_db) as connection:
        assert connection.execute("SELECT * FROM migration_probe ORDER BY position").fetchall() == [(1, "second"), (2, "third")]
        assert connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall() == [(1,), (2,), (3,)]
    before = snapshot(legacy_db, include_metadata=True)
    assert migrate_database(legacy_db, registry) == ()
    assert snapshot(legacy_db, include_metadata=True) == before


@pytest.mark.parametrize("registry", [
    (), (BASELINE, BASELINE), (BASELINE, SECOND, SECOND),
    (BASELINE, THIRD), (Migration(0, ("SELECT 1",)),),
    (Migration(True, ("SELECT 1",)),), (Migration("1", ("SELECT 1",)),),
    (Migration(1, ("CREATE TABLE wrong(id INTEGER)",)),),
    (BASELINE, Migration(2, ())), (BASELINE, Migration(2, ["SELECT 1"])),
    (BASELINE, Migration(2, ("",))), (BASELINE, Migration(2, (None,))),
])
def test_invalid_registry_fails_before_database_creation(tmp_path, registry):
    path = tmp_path / "not-created.db"
    with pytest.raises(MigrationError):
        migrate_database(path, registry)
    assert not path.exists()


def test_unknown_newer_version_and_missing_history_are_rejected(legacy_db, snapshot):
    migrate_database(legacy_db, (BASELINE, SECOND, THIRD))
    before = snapshot(legacy_db, include_metadata=True)
    with pytest.raises(MigrationError, match="newer than this application"):
        migrate_database(legacy_db)
    assert snapshot(legacy_db, include_metadata=True) == before
    with sqlite3.connect(legacy_db) as connection:
        connection.execute("DELETE FROM schema_migrations WHERE version=2")
    before = snapshot(legacy_db, include_metadata=True)
    with pytest.raises(MigrationError, match="contiguous prefix"):
        migrate_database(legacy_db, (BASELINE, SECOND, THIRD))
    assert snapshot(legacy_db, include_metadata=True) == before


@pytest.mark.parametrize("adopted_first", [False, True])
def test_failed_batch_rolls_back_ddl_user_updates_and_ledger(legacy_db, snapshot, adopted_first):
    if adopted_first:
        migrate_database(legacy_db)
    before = snapshot(legacy_db, include_metadata=True)
    failing = Migration(3, (
        "UPDATE messages SET content='must roll back' WHERE id=17",
        "UPDATE memory_items SET content='must roll back FTS' WHERE id=41",
        "INSERT INTO missing_table VALUES (1)",
    ))
    with pytest.raises(MigrationError):
        migrate_database(legacy_db, (BASELINE, SECOND, failing))
    assert legacy_db.is_file()
    assert snapshot(legacy_db, include_metadata=True) == before
    with sqlite3.connect(legacy_db) as connection:
        assert connection.execute("SELECT rowid FROM memory_items_fts WHERE memory_items_fts MATCH 'Atlas'").fetchall() == [(41,)]
    assert migrate_database(legacy_db, (BASELINE, SECOND, THIRD)) == ((2, 3) if adopted_first else (1, 2, 3))


def test_previous_committed_migrations_survive_later_failure(legacy_db, snapshot):
    migrate_database(legacy_db, (BASELINE, SECOND))
    before = snapshot(legacy_db, include_metadata=True)
    failing = Migration(3, ("INSERT INTO migration_probe VALUES (9, 'rollback')", "invalid SQL"))
    with pytest.raises(MigrationError):
        migrate_database(legacy_db, (BASELINE, SECOND, failing))
    assert snapshot(legacy_db, include_metadata=True) == before


def test_fresh_database_failure_leaves_no_partial_schema(tmp_path):
    path = tmp_path / "fresh-failure.db"
    failing = Migration(2, ("CREATE TABLE temporary_probe(id INTEGER)", "INSERT INTO missing_table VALUES(1)"))
    with pytest.raises(MigrationError):
        migrate_database(path, (BASELINE, failing))
    assert path.exists()  # The runner never deletes a failed database file.
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM sqlite_schema").fetchall() == []
    assert migrate_database(path) == (1,)


@pytest.mark.parametrize("statement", [
    "COMMIT", "END TRANSACTION", "ROLLBACK", "BEGIN", "SAVEPOINT escape", "RELEASE escape",
    "PRAGMA foreign_keys=OFF", "PRAGMA journal_mode=OFF", "VACUUM", "ATTACH ':memory:' AS another",
    "DROP TABLE sessions", "ALTER TABLE settings DROP COLUMN value",
    "DELETE FROM schema_migrations", "UPDATE schema_migrations SET applied_at='wrong'",
    "INSERT INTO schema_migrations VALUES(999, 'wrong')",
    "CREATE TRIGGER ledger_hook AFTER INSERT ON schema_migrations BEGIN DELETE FROM messages; END",
    "CREATE TEMP TABLE local_only(id INTEGER)",
    "CREATE TABLE one(id INTEGER); COMMIT;",
])
def test_migration_cannot_override_transaction_or_ledger(legacy_db, snapshot, statement):
    migrate_database(legacy_db)
    before = snapshot(legacy_db, include_metadata=True)
    with pytest.raises(MigrationError):
        migrate_database(legacy_db, (BASELINE, Migration(2, (
            "UPDATE messages SET content='must roll back' WHERE id=17", statement,
        ))))
    assert snapshot(legacy_db, include_metadata=True) == before


def test_foreign_keys_are_enforced_for_new_migrations(legacy_db, snapshot):
    before = snapshot(legacy_db)
    bad = Migration(2, ("INSERT INTO messages(session_id, role, content, created_at) VALUES ('missing', 'user', 'invalid', 'now')",))
    with pytest.raises(MigrationError) as caught:
        migrate_database(legacy_db, (BASELINE, bad))
    assert isinstance(caught.value.__cause__, sqlite3.IntegrityError)
    assert snapshot(legacy_db) == before


def test_additive_schema_migration_is_replayable_without_reapplying(legacy_db):
    additive = Migration(2, (
        "ALTER TABLE messages ADD COLUMN external_id TEXT",
        "CREATE INDEX messages_external_id ON messages(external_id)",
    ))
    assert migrate_database(legacy_db, (BASELINE, additive)) == (1, 2)
    assert migrate_database(legacy_db, (BASELINE, additive)) == ()
    with sqlite3.connect(legacy_db) as connection:
        assert connection.execute("SELECT id, content, external_id FROM messages ORDER BY id").fetchall() == [
            (17, "  Nicht umschreiben: Grüße!  ", None), (18, "Bestätigt.", None)
        ]


def test_existing_data_constraint_failure_rolls_back_adoption(legacy_db, snapshot):
    before = snapshot(legacy_db, include_metadata=True)
    invalid = Migration(2, ("CREATE UNIQUE INDEX invalid_unique_session ON messages(session_id)",))
    with pytest.raises(MigrationError) as caught:
        migrate_database(legacy_db, (BASELINE, invalid))
    assert isinstance(caught.value.__cause__, sqlite3.IntegrityError)
    assert snapshot(legacy_db, include_metadata=True) == before
