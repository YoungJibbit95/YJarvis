"""Versioned SQLite initialization; not a V2 domain/runtime integration layer."""

from .errors import MigrationError
from .runner import migrate_database

__all__ = ["MigrationError", "migrate_database"]
