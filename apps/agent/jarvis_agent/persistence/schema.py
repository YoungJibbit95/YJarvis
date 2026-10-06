"""Conservative structural recognition and integrity checks; never repair data."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .errors import MigrationError
from .sql import sql_tokens

METADATA_SQL = """CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    applied_at TEXT NOT NULL
)"""
METADATA_KEY = ("table", "schema_migrations")
SchemaSignature = dict[tuple[str, str], tuple[str, tuple[str, ...]]]


def schema_signature(connection: sqlite3.Connection) -> SchemaSignature:
    rows = connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_schema "
        "WHERE name NOT GLOB 'sqlite_*' ORDER BY type, name"
    ).fetchall()
    return {(kind, name): (table, sql_tokens(sql or "")) for kind, name, table, sql in rows}


def require_schema(actual: SchemaSignature, expected: SchemaSignature) -> None:
    missing = sorted(key[1] for key in expected.keys() - actual.keys())
    extra = sorted(key[1] for key in actual.keys() - expected.keys())
    changed = sorted(key[1] for key in expected.keys() & actual.keys() if actual[key] != expected[key])
    if missing or extra or changed:
        raise MigrationError(
            f"Unrecognized or inconsistent schema (missing={missing}, extra={extra}, changed={changed})."
        )


def read_history(connection: sqlite3.Connection, latest: int) -> tuple[int, ...]:
    rows = connection.execute("SELECT version, applied_at FROM schema_migrations ORDER BY version").fetchall()
    if not rows:
        raise MigrationError("Migration ledger exists but contains no baseline entry.")
    versions = tuple(row[0] for row in rows)
    if any(type(version) is not int or version < 1 for version in versions):
        raise MigrationError("Invalid migration version in database.")
    if versions[-1] > latest:
        raise MigrationError("Database is newer than this application; use a compatible version.")
    if versions != tuple(range(1, len(versions) + 1)):
        raise MigrationError("Migration history is not a contiguous prefix of the registry.")
    for _, applied_at in rows:
        try:
            timestamp = datetime.fromisoformat(applied_at)
            if timestamp.utcoffset() is None:
                raise ValueError("naive timestamp")
        except (TypeError, ValueError) as exc:
            raise MigrationError("Invalid applied_at timestamp in migration ledger.") from exc
    return versions


def check_integrity(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise MigrationError("SQLite integrity check failed.")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise MigrationError("Existing foreign-key violations; automatic repair is forbidden.")
    # rank=1 checks the external content against the index, not just FTS internals.
    # This is FTS5's validation command, NOT a rebuild or a user-row insertion.
    connection.execute(
        "INSERT INTO memory_items_fts(memory_items_fts, rank) VALUES ('integrity-check', 1)"
    ).close()
