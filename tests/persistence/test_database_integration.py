"""Exercise the unchanged asynchronous Database API against real SQLite files."""

import asyncio
import sqlite3
from functools import partial

import pytest

from jarvis_agent.db import DEFAULT_SETTINGS, DEFAULT_SMARTHOME_ENTITIES, Database
from jarvis_agent.persistence import MigrationError, migrate_database
from jarvis_agent.persistence.registry import BASELINE, Migration


def database(path):
    return Database(path, path.parent, path.parent / "model.bin")


def test_fresh_database_init_preserves_defaults_and_is_idempotent(tmp_path, snapshot):
    path = tmp_path / "fresh.db"
    db = database(path)

    async def check():
        await db.init()
        first = snapshot(path, include_metadata=True)
        await db.init()
        await db.init()
        assert snapshot(path, include_metadata=True) == first
        settings = await db.get_settings()
        for key, value in DEFAULT_SETTINGS.items():
            assert settings[key] == str(value)
        assert settings["allowed_paths"] == [str(path.parent)]
        assert len(await db.list_smarthome_entities()) == len(DEFAULT_SMARTHOME_ENTITIES)
        async with db._connect() as connection:
            assert tuple(await db._fetchone(connection, "PRAGMA foreign_keys")) == (1,)
            assert tuple(await db._fetchone(connection, "PRAGMA journal_mode")) == ("wal",)
            assert [tuple(row) for row in await db._fetchall(
                connection, "SELECT version FROM schema_migrations"
            )] == [(1,)]
    asyncio.run(check())


def test_populated_v1_init_preserves_every_row_and_existing_api(legacy_db, snapshot):
    before = snapshot(legacy_db)
    db = database(legacy_db)

    async def check():
        await db.init()
        await db.init()
        assert snapshot(legacy_db) == before
        assert await db.session_exists("legacy-session")
        assert await db.count_messages("legacy-session") == 2
        messages = await db.list_messages("legacy-session")
        assert [item["id"] for item in messages] == [17, 18]
        assert messages[0]["content"] == "  Nicht umschreiben: Grüße!  "
        assert (await db.get_settings())["model_name"] == "custom-local-model"
        assert (await db.get_approval("legacy-approval"))["status"] == "pending"
        assert (await db.list_pending_approvals())[0]["tool_input"] == {"app": "Safari"}
        assert (await db.get_learned_command("fokus"))["usage_count"] == 9
        assert (await db.find_matching_learned_command("Fokus jetzt"))["trigger"] == "fokus"
        assert (await db.get_tool_learning_stats(tool_names=["open_app"]))[0]["average_latency_ms"] == 12.75
        assert (await db.search_memory("Atlas"))[0]["id"] == 41
        assert (await db.get_smarthome_entity("light.custom"))["attributes"] == {"brightness": 73}
        # Read operations must not rewrite or normalize historical rows either.
        assert snapshot(legacy_db) == before
    asyncio.run(check())


def test_legacy_crud_remains_usable_after_adoption(legacy_db):
    db = database(legacy_db)

    async def check():
        await db.init()
        await db.create_session("new-session")
        message_id = await db.add_message("new-session", "user", "Neuer Eintrag")
        assert message_id > 18
        assert (await db.list_recent_messages("new-session"))[0]["content"] == "Neuer Eintrag"
        await db.create_approval("new-approval", "new-session", "new-run", "open_app", {"app": "Notes"})
        await db.resolve_approval("new-approval", "denied", "deny")
        assert (await db.get_approval("new-approval"))["decision"] == "deny"
        await db.add_tool_run("new-run", "new-session", "new-tool", "open_app", {}, False, None, "example")
        await db.add_memory_item("new-session", "Quasar Notiz", 0.75)
        assert (await db.search_memory("Quasar"))[0]["content"] == "Quasar Notiz"
        command = await db.upsert_learned_command(trigger="Neuer Fokus", tool_name="open_app", tool_input={"app": "Notes"})
        assert command["trigger"] == "neuer fokus"
        await db.record_learned_command_result("neuer fokus", True)
        assert (await db.get_learned_command("neuer fokus"))["success_count"] == 1
        assert len(await db.list_learned_commands()) == 2
        await db.record_tool_learning(tool_name="new-tool", success=True, latency_ms=12)
        assert (await db.get_tool_learning_stats(tool_names=["new-tool"]))[0]["last_latency_ms"] == 12
        assert (await db.update_settings({"language": "de"}))["language"] == "de"
        entity = await db.update_smarthome_entity("light.custom", "off", {"brightness": 0})
        assert entity["state"] == "off"
        assert await db.delete_learned_command("neuer fokus")
        await db.init()
        assert await db.count_messages("new-session") == 1
    asyncio.run(check())
    with sqlite3.connect(legacy_db) as connection:
        assert connection.execute("SELECT error FROM tool_runs WHERE id='new-tool'").fetchone() == ("example",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_inconsistent_v1_fails_before_wal_or_default_seeding(tmp_path, make_legacy, legacy_statements, snapshot):
    path = make_legacy(tmp_path / "partial.db", statements=legacy_statements[:1], populate=False)
    before_bytes = path.read_bytes()
    before = snapshot(path)
    with pytest.raises(MigrationError, match="inconsistent schema"):
        asyncio.run(database(path).init())
    assert path.read_bytes() == before_bytes
    assert snapshot(path) == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)


def test_real_migration_failure_prevents_defaults_and_preserves_database(legacy_db, snapshot, monkeypatch):
    before = snapshot(legacy_db, include_metadata=True)
    failing = Migration(2, (
        "UPDATE messages SET content='rollback' WHERE id=17",
        "INSERT INTO missing_table VALUES (1)",
    ))
    monkeypatch.setattr("jarvis_agent.db.migrate_database", partial(migrate_database, migrations=(BASELINE, failing)))
    with pytest.raises(MigrationError):
        asyncio.run(database(legacy_db).init())
    assert snapshot(legacy_db, include_metadata=True) == before
    with sqlite3.connect(legacy_db) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
