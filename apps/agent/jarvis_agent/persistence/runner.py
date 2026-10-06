"""Forward-only SQLite startup migration, with atomic adoption and batch rollback."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .errors import MigrationError
from .registry import BASELINE, MIGRATIONS, Migration, ordered_migrations
from .schema import (
    METADATA_KEY, METADATA_SQL, check_integrity, read_history,
    require_schema, schema_signature,
)
from .sql import execute_statements


def _record(connection: sqlite3.Connection, version: int) -> None:
    connection.execute(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (version, datetime.now(timezone.utc).isoformat()),
    ).close()


def _migrate_locked(connection: sqlite3.Connection, reference: sqlite3.Connection,
                    migrations: tuple[Migration, ...]) -> tuple[int, ...]:
    baseline_schema = schema_signature(reference)
    reference.execute(METADATA_SQL).close()
    expected_metadata = schema_signature(reference)[METADATA_KEY]
    actual = schema_signature(connection)
    applied: tuple[int, ...] = ()
    recorded: list[int] = []

    if actual and METADATA_KEY in actual:
        if actual[METADATA_KEY] != expected_metadata:
            raise MigrationError("Unrecognized migration ledger schema.")
        applied = read_history(connection, migrations[-1].version)
        for migration in migrations[1:len(applied)]:
            execute_statements(reference, migration.statements)
        require_schema(actual, schema_signature(reference))
        check_integrity(connection)
    else:
        if actual:
            # No ledger does NOT mean empty. Require the entire frozen V1 schema,
            # including FTS5/shadow definitions and all three original triggers.
            require_schema(actual, baseline_schema)
            check_integrity(connection)
        else:
            if connection.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone() is not None:
                raise MigrationError("Internal-only schema is not a fresh database.")
            execute_statements(connection, BASELINE.statements)
        connection.execute(METADATA_SQL).close()
        require_schema(schema_signature(connection), schema_signature(reference))
        check_integrity(connection)
        _record(connection, 1)
        recorded.append(1)
        applied = (1,)

    for migration in migrations[len(applied):]:
        execute_statements(connection, migration.statements)
        # Replay schema history only in a disposable empty reference database.
        # Never reconstruct, replace or copy the actual user database.
        execute_statements(reference, migration.statements)
        require_schema(schema_signature(connection), schema_signature(reference))
        check_integrity(connection)
        _record(connection, migration.version)
        recorded.append(migration.version)
    return tuple(recorded)


def migrate_database(db_path: Path, migrations: Sequence[Migration] = MIGRATIONS,
                     *, timeout: float = 5.0) -> tuple[int, ...]:
    """Return newly recorded versions (including an adopted baseline).

    The complete pending batch is one BEGIN IMMEDIATE transaction. All new DDL,
    data changes and ledger entries commit together or roll back together. Earlier
    committed versions survive failure. Never change the user's journal mode here.
    Database.init configures WAL and seeds the unchanged defaults only on success.
    """
    ordered = ordered_migrations(migrations)
    try:
        with closing(sqlite3.connect(":memory:", isolation_level=None, cached_statements=0)) as reference:
            reference.execute("PRAGMA foreign_keys = ON").close()
            reference.execute("BEGIN").close()
            execute_statements(reference, BASELINE.statements)
            with closing(sqlite3.connect(db_path, isolation_level=None, timeout=timeout,
                                         cached_statements=0)) as connection:
                connection.execute("PRAGMA foreign_keys = ON").close()
                if connection.execute("PRAGMA foreign_keys").fetchone() != (1,):
                    raise MigrationError("SQLite foreign-key enforcement is unavailable.")
                if connection.execute("PRAGMA journal_mode").fetchone()[0] not in {
                    "delete", "truncate", "persist", "wal"
                }:
                    raise MigrationError("An on-disk rollback-capable journal mode is required.")
                connection.execute("BEGIN IMMEDIATE").close()
                try:
                    if connection.execute("PRAGMA user_version").fetchone() != (0,) or (
                        connection.execute("PRAGMA application_id").fetchone() != (0,)
                    ):
                        raise MigrationError("Unrecognized SQLite header version/application ID.")
                    recorded = _migrate_locked(connection, reference, ordered)
                    connection.commit()
                    return recorded
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise
    except sqlite3.Error as exc:
        raise MigrationError(f"SQLite migration failed ({type(exc).__name__}).") from exc
