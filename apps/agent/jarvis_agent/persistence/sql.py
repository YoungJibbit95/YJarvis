"""One-statement execution with transaction/metadata guardrails, not a SQL sandbox."""

from __future__ import annotations

import re
import sqlite3

from .errors import MigrationError

# Preserve quoted literals/identifiers: whitespace inside a string is meaningful.
_TOKENS = re.compile(
    r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|\[[^\]]*\]"
    r"|--[^\n]*|/\*.*?\*/|[A-Za-z_][A-Za-z_0-9]*|[0-9]+(?:\.[0-9]+)?|\S",
    re.DOTALL,
)
_FORBIDDEN = {
    sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT,
    sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH,
    sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_DROP_VTABLE,
    sqlite3.SQLITE_DROP_INDEX, sqlite3.SQLITE_DROP_TRIGGER, sqlite3.SQLITE_DROP_VIEW,
    sqlite3.SQLITE_CREATE_TEMP_TABLE, sqlite3.SQLITE_CREATE_TEMP_INDEX,
    sqlite3.SQLITE_CREATE_TEMP_TRIGGER, sqlite3.SQLITE_CREATE_TEMP_VIEW,
}


def sql_tokens(sql: str) -> tuple[str, ...]:
    tokens = [
        token if token[0] in "'\"`[" else token.lower()
        for token in _TOKENS.findall(sql)
        if not token.startswith(("--", "/*"))
    ]
    while tokens and tokens[-1] == ";":
        tokens.pop()
    return tuple(tokens)


def _authorize(action: int, arg1: str | None, arg2: str | None,
               database: str | None, source: str | None) -> int:
    if action in _FORBIDDEN or database not in (None, "main"):
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA:
        # FTS5 internally reads data_version; migrations may not change PRAGMAs.
        return sqlite3.SQLITE_OK if arg1 == "data_version" and arg2 is None else sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and arg2 in ("load_extension", "readfile", "writefile"):
        return sqlite3.SQLITE_DENY
    if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
        if arg1 == "schema_migrations":
            return sqlite3.SQLITE_DENY
    if action in (sqlite3.SQLITE_ALTER_TABLE, sqlite3.SQLITE_CREATE_TRIGGER, sqlite3.SQLITE_CREATE_INDEX) and arg2 == "schema_migrations":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def execute_statements(connection: sqlite3.Connection, statements: tuple[str, ...]) -> None:
    """The runner, never a migration, owns BEGIN/COMMIT/ROLLBACK and the ledger."""
    if not connection.in_transaction:
        raise MigrationError("Migration execution requires an explicit transaction.")
    connection.set_authorizer(_authorize)
    try:
        for sql in statements:
            tokens = sql_tokens(sql)
            if not tokens or tokens[0] not in {"create", "alter", "insert", "update", "delete"}:
                raise MigrationError("Migration contains an unsupported SQL statement.")
            if tokens[0] == "alter" and "drop" in tokens:
                raise MigrationError("Destructive ALTER statements are not supported.")
            # execute(), unlike executescript(), cannot implicitly commit a batch.
            connection.execute(sql).close()
            if not connection.in_transaction:
                raise MigrationError("Migration unexpectedly ended its transaction.")
    finally:
        connection.set_authorizer(None)
