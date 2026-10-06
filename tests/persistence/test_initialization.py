import sqlite3
from datetime import datetime

from jarvis_agent.persistence import migrate_database
from jarvis_agent.persistence.schema import schema_signature


def test_fresh_file_receives_exact_legacy_schema_and_one_version(tmp_path, make_legacy, snapshot):
    fresh = tmp_path / "fresh.db"
    old = make_legacy(tmp_path / "old-empty.db", populate=False)
    assert not fresh.exists()
    assert migrate_database(fresh) == (1,)
    with sqlite3.connect(fresh) as connection, sqlite3.connect(old) as legacy:
        actual = schema_signature(connection)
        actual.pop(("table", "schema_migrations"))
        assert actual == schema_signature(legacy)
        history = connection.execute("SELECT version, applied_at FROM schema_migrations").fetchall()
    assert len(history) == 1 and history[0][0] == 1
    assert datetime.fromisoformat(history[0][1]).utcoffset() is not None
    before = snapshot(fresh, include_metadata=True)
    assert migrate_database(fresh) == ()
    assert migrate_database(fresh) == ()
    assert snapshot(fresh, include_metadata=True) == before


def test_existing_zero_byte_file_is_fresh(tmp_path):
    path = tmp_path / "zero.db"
    path.touch()
    assert migrate_database(path) == (1,)


def test_legacy_adoption_preserves_every_raw_row_and_fts_shadow_row(legacy_db, snapshot):
    before = snapshot(legacy_db)
    with sqlite3.connect(legacy_db) as connection:
        original_schema = schema_signature(connection)
        assert connection.execute("SELECT rowid FROM memory_items_fts WHERE memory_items_fts MATCH 'Atlas'").fetchall() == [(41,)]
    assert migrate_database(legacy_db) == (1,)
    assert snapshot(legacy_db) == before
    with sqlite3.connect(legacy_db) as connection:
        current = schema_signature(connection)
        current.pop(("table", "schema_migrations"))
        assert current == original_schema
        assert connection.execute("SELECT rowid FROM memory_items_fts WHERE memory_items_fts MATCH 'Atlas'").fetchall() == [(41,)]
    adopted = snapshot(legacy_db, include_metadata=True)
    assert migrate_database(legacy_db) == ()
    assert snapshot(legacy_db, include_metadata=True) == adopted


def test_fts_insert_update_and_delete_triggers_still_work(legacy_db):
    migrate_database(legacy_db)
    with sqlite3.connect(legacy_db) as connection:
        match = lambda term: connection.execute(
            "SELECT rowid FROM memory_items_fts WHERE memory_items_fts MATCH ? ORDER BY rowid", (term,)
        ).fetchall()
        connection.execute("INSERT INTO memory_items VALUES (60, 'legacy-session', 'Insertbeweis', 0.5, 'old timestamp')")
        assert match("Insertbeweis") == [(60,)]
        connection.execute("UPDATE memory_items SET content='Updatebeweis' WHERE id=60")
        assert match("Insertbeweis") == []
        assert match("Updatebeweis") == [(60,)]
        connection.execute("DELETE FROM memory_items WHERE id=60")
        assert match("Updatebeweis") == []
        assert match("Atlas") == [(41,)]


def test_foreign_key_actions_and_autoincrement_are_preserved(legacy_db):
    migrate_database(legacy_db)
    with sqlite3.connect(legacy_db) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        cursor = connection.execute("INSERT INTO messages(session_id,role,content,created_at) VALUES ('legacy-session','user','new','now')")
        assert cursor.lastrowid == 19
        connection.execute("DELETE FROM sessions WHERE id='legacy-session'")
        for table in ("messages", "approvals", "tool_runs"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,)
        assert connection.execute("SELECT session_id FROM memory_items WHERE id=41").fetchone() == (None,)
        assert connection.execute("SELECT rowid FROM memory_items_fts WHERE memory_items_fts MATCH 'Atlas'").fetchall() == [(41,)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_no_v2_domain_tables_are_created(tmp_path):
    path = tmp_path / "fresh.db"
    migrate_database(path)
    with sqlite3.connect(path) as connection:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_schema")}
    assert not names & {"turns", "plans", "plan_actions", "observations", "policy_decisions", "trust_rules", "memories_v2", "routines"}
