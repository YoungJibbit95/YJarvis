# YJ2-02: persistence migration framework

## Scope and baseline

This implements the migration foundation in architecture section 18.1 and roadmap
PR 02. The [supplied architecture](YJarvis_V2_Architecture_and_Browser_Agent_Master_Prompt.md)
and the accepted [domain contracts](domain-contracts-v2.md) are unchanged.

PR #2 was externally accepted and squash-merged as
`744fd50e499acd0656b9592cbf4b3e6805e97e57`. The four checks in main push CI run
`37505931941` passed, and main HEAD was read again, before the YJ2-02 branch was
created from that exact commit. The original architecture baseline differs only
by accepted YJ2-00 and YJ2-01 work.

Only `Database.init()` gains a migration call instead of its large DDL script.
The existing `Database` remains the compatibility boundary; its CRUD methods and
callers do not move. No speculative repository interfaces are added. No Domain
Contracts are imported into persistence or runtime. There are no new V2 tables,
TurnEngine, planner, policy, executor, voice, memory or routines changes.

## Files and ownership

`jarvis_agent/persistence/` contains small, separate responsibilities:

| Module | Purpose |
| --- | --- |
| `migrations/v001_baseline.py` | Frozen V1 table, FTS5 and trigger definitions |
| `registry.py` | Immutable migration descriptors and explicit ordered registry |
| `runner.py` | Connection/transaction ownership and startup paths |
| `schema.py` | Schema recognition, ledger validation and integrity checks |
| `sql.py` | Statement execution and transaction/ledger guardrails |
| `errors.py` | Fail-closed error and recovery guidance |

The runner uses Python's existing `sqlite3` module. `Database.init()` awaits it
with `asyncio.to_thread`, so its connection stays entirely in its worker thread.
The application's existing aiosqlite 0.20.0 connections and dependencies stay
unchanged. No migration framework or dependency upgrade is introduced.

## Version model

The only shipped migration is version **1**, the existing V1 schema. Migration
versions are independent of YJ2 roadmap/PR numbers. The explicit registry accepts
positive integer versions, sorts them ascending, rejects duplicates and gaps,
and requires the exact frozen version-1 descriptor. Validate the registry before
opening a user database. SQL consists of individual statements, with each complete
trigger body kept as one statement; there is no fragile semicolon split in the runner.

The only added production table is:

```sql
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    applied_at TEXT NOT NULL
);
```

An applied history must be a nonempty contiguous prefix of the application's
registry, with valid timezone-aware ISO timestamps. An unknown newer version,
missing historical version, malformed ledger or ledger without a baseline fails
closed. Never edit/delete applied entries to persuade an older app to start.
Published migrations are append-only review artifacts; this minimal ledger does
not store SQL checksums and is not tamper-proof.

## Fresh database

A missing file, zero-byte file or empty SQLite database with **no schema objects**
and unset `user_version`/`application_id` is fresh. A database containing only
SQLite internal objects is not silently treated as fresh.

Inside the migration transaction, create the frozen V1 schema, create the ledger,
validate schema/integrity, and record version 1. Any subsequent registered
migrations run in the same pending batch. Only after successful commit does
`Database.init()` configure the existing WAL connection and run its unchanged
legacy default-seeding code.

Schema commit and default seeding are deliberately separate transactions, as
before. A seed failure is not a failed schema migration: the valid schema remains
and existing idempotent seeding can be retried. No schema failure proceeds to seeds.

## Legacy adoption: no ledger does not mean no data

A database with schema objects but no ledger must match the **complete frozen V1
schema**, not a single-table or file-existence heuristic. Recognition compares
`sqlite_schema` object kind, name, owning table and tokenized defining SQL against
a disposable reference built with the same SQLite engine and registered schema.
It includes all ten runtime tables, their types/defaults/keys/foreign-key clauses,
the external-content FTS5 table and its shadow definitions, and all three original
memory insert/update/delete triggers. Constraints embedded in CREATE statements
remain part of the signature. SQLite's own `sqlite_*` objects are excluded from
this structural comparison; their existing contents are not rewritten.

Tokenization ignores SQL formatting/comments and unquoted keyword case, but
preserves quoted text, literal whitespace and identifiers. It is a conservative
known-schema recognizer, **not a general SQL-equivalence engine**. Extra custom
indexes/tables/views/triggers and otherwise equivalent but differently quoted
schema variants require manual review rather than automatic acceptance.

Recognition is followed by `PRAGMA integrity_check`, `PRAGMA foreign_key_check`
and FTS5's external-content integrity check. A matching schema with orphan rows
or an out-of-sync FTS index is not accepted. The runner never rebuilds the index.
Nonzero SQLite header application/version markers also require explicit review.

For a recognized, consistent V1 database, **do not execute baseline CREATE
statements on that database**. Add only the ledger and version-1 entry. Existing
IDs, text, JSON strings, timestamps, settings, allowlists, counters and FTS contents
are not normalized or rewritten. Tests snapshot every table, including FTS shadow
rows and `sqlite_sequence`, before and after adoption.

The later, unchanged legacy default-seeding code still inserts missing settings
and the project path and populates smart-home examples only when that table is
empty. Those existing startup semantics are not redefined as migrations; existing
rows are not overwritten. Tests with populated V1 settings/entities prove no row
changes across the complete new `Database.init()` path, repeated twice.

## Already migrated database

Under the same writer lock, verify the ledger's exact known shape/history and the
expected schema for its last applied version. Applied SQL is replayed **only in
the disposable empty reference**, never in the user's database. Then validate
integrity and apply only the missing suffix. Repeated startup with no pending
versions leaves all ledger timestamps and user rows unchanged.

Reference replay is a deliberately small design: future registered statements
must also work on an empty baseline. Arbitrary data-dependent Python callbacks,
external files, attached databases or migrations requiring nontransactional
maintenance are not supported by this framework. They require a separate reviewed
design, not an ad-hoc bypass. This step provides only the unchanged baseline SQL.

## SQLite transaction and failure behavior

The runner explicitly enables and verifies foreign keys **before** beginning a
transaction. It owns one `BEGIN IMMEDIATE` and one commit for the entire pending
batch, including baseline adoption when needed. This serializes competing startup
writers. Schema changes, data changes, trigger effects and all newly applied ledger
entries commit together. A failed statement, failed integrity check, unexpected
exception or busy commit rolls back the complete pending batch. Versions committed
by an earlier successful invocation remain intact. No failed version is left
marked as applied. A new file may remain empty after rollback; it is never deleted.

Production migrations use `execute()` for each statement, **not `executescript()`**:
Python's script API implicitly commits a pending transaction before running the
script. SQLite CREATE/ALTER/DML changes used here are tested inside the explicit
transaction, including FTS/trigger changes. Transaction control, DROP operations,
destructive ALTER, PRAGMA changes, VACUUM, attached/temp databases and ledger
writes from migration SQL are rejected. An authorizer provides a second guard
against transaction/ledger interference; this is not a sandbox for untrusted SQL.
Migration definitions remain trusted, reviewed application code.

The runner preserves an existing rollback-capable journal mode and does not try
to switch it inside a transaction. Disk databases in OFF/MEMORY modes are rejected.
On success the existing runtime connection retains its normal WAL behavior. WAL
and SHM files belong to SQLite; the application never unlinks them. Tests retain
live WAL connections and a reader snapshot during adoption, and check preservation
of committed content still present in WAL. A rollback-journal reader blocking
COMMIT is also tested; rollback removes the uncommitted ledger/DDL.

FTS5 must be available. Its `integrity-check` command with `rank=1` checks the
external content table against the index. This validation command is expressed
as an INSERT into FTS's control column, but is not insertion of a memory item or
an index rebuild. Tests cover insert/update/delete triggers and stale-index
rejection. No FTS schema is replaced. Existing FK CASCADE/SET NULL semantics remain.

Full integrity/FTS scans hold the startup writer lock and cost work proportional
to database size; no latency claim is made. The timeout defaults to five seconds,
then startup reports an error, not an automatic repair. No network filesystem,
power-loss/fault-injection or real macOS durability result is claimed. SQLite and
the underlying filesystem still determine crash durability. Cancelling the async
await does not forcibly stop `to_thread`: the worker can finish its atomic commit
or rollback. Do not interpret coroutine cancellation as proof that no migration ran.

## Adding a later migration

Add one reviewed module under `persistence/migrations/`, containing a tuple of
complete SQL statements, and append its `Migration(next_version, STATEMENTS)` to
`MIGRATIONS`. Keep old modules unchanged. Add file-backed tests for fresh installs,
all supported prior histories, realistic data, repeated startup and a mid-batch
failure. Ensure the schema can be replayed on the empty reference and that all
legacy integrity checks still hold. Schema changing the memory/FTS assumptions
must update the explicit validation contract in that approved roadmap step.

Do not put future DDL back into `Database.init()`. Do not add `turns`, `plans`,
`observations`, policy/trust, memory V2 or routines tables until their own approved
integration step. Domain isolation tests stay unchanged in YJ2-02.

## Recovery and rollback

On an unknown/partial/newer/corrupt schema, startup stops with `MigrationError`
and a recovery hint. It never deletes a database, drops its tables, changes rows
to fit assumptions, overwrites it from a template, or retries by recreating it.
Stop the application. Preserve the database **and any WAL/SHM sidecars together**;
use a consistent SQLite backup or a stopped-application copy. Diagnose on a copy
with the matching application/schema version. Restore a verified backup only by
an explicit owner action. Do not delete the original, ledger, or sidecars to
suppress the error. Unknown-schema rejection may require a specific reviewed
adoption path; it does not mean the data is disposable.

Code rollback is a revert of this isolated PR, not a down-migration. Preserve the
ledger and user data. The prior V1 initializer ignores the extra ledger table;
there is no automatic removal or rollback of schema versions. Future migrations
must document their own compatibility and rollback limits.

## Evidence and boundaries

`tests/fixtures/legacy_v1_schema.sql` is an independent snapshot of original
`db.py` at `744fd50e...`, Git blob `e2832f9f689bd2d7cf2c2ebdc617e274d3a04030`.
It is not generated from the new migration at test time. All persistence tests
use real temporary SQLite files; no personal `runtime/jarvis.db` is opened.
Run `python -m pytest tests/persistence -q`, then the unchanged full suite/lint
and desktop checks. Actual environments and results belong in the PR evidence.

Known baseline risks remain separate: YJ2-00 reported 21 npm findings (2 critical,
11 high); no server-side main protection; no interactive macOS/Apple Silicon smoke
verification here; transitive Python dependencies are not fully locked. None is
remediated or declared cleared by this PR. Stop for external review; do not merge
YJ2-02 or begin YJ2-03/TurnEngine work.

### SQLite references checked during implementation

- [SQLite transaction control](https://www.sqlite.org/lang_transaction.html)
- [Python 3.11 sqlite3 transaction control](https://docs.python.org/3.11/library/sqlite3.html#transaction-control)
- [SQLite PRAGMA foreign_keys and journal_mode](https://www.sqlite.org/pragma.html)
- [FTS5 integrity-check and external content](https://www.sqlite.org/fts5.html#the_integrity_check_command)
