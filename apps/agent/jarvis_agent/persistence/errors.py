"""Initialization failures must preserve the database, not silently repair it."""

RECOVERY = (
    "Startup stopped; no automatic repair or database deletion was attempted. "
    "Stop YJarvis, preserve the database together with any WAL/SHM sidecars, "
    "and inspect a backup with a compatible application version. "
    "See docs/architecture/persistence-migrations.md."
)


class MigrationError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"{reason} {RECOVERY}")
