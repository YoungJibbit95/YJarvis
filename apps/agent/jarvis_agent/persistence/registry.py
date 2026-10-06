"""Small explicit registry. Migration numbering is independent of YJ2 PR numbers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .errors import MigrationError
from .migrations.v001_baseline import STATEMENTS


@dataclass(frozen=True)
class Migration:
    version: int
    statements: tuple[str, ...]


BASELINE = Migration(version=1, statements=STATEMENTS)
MIGRATIONS = (BASELINE,)


def ordered_migrations(migrations: Sequence[Migration]) -> tuple[Migration, ...]:
    """Reject malformed registries before opening any user database."""
    entries = tuple(migrations)
    if not entries:
        raise MigrationError("Migration registry is empty.")
    for entry in entries:
        if not isinstance(entry, Migration) or type(entry.version) is not int or entry.version < 1:
            raise MigrationError("Migration versions must be positive integers.")
        if not isinstance(entry.statements, tuple) or not entry.statements or not all(
            isinstance(sql, str) and sql.strip() for sql in entry.statements
        ):
            raise MigrationError("Each migration requires a nonempty tuple of SQL statements.")
    versions = [entry.version for entry in entries]
    if len(versions) != len(set(versions)):
        raise MigrationError("Duplicate migration versions.")
    ordered = tuple(sorted(entries, key=lambda entry: entry.version))
    if [entry.version for entry in ordered] != list(range(1, len(ordered) + 1)):
        raise MigrationError("Migration versions must be contiguous, starting at 1.")
    if ordered[0] != BASELINE:
        raise MigrationError("Version 1 must be the frozen V1 baseline.")
    return ordered
