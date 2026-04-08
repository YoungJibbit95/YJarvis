from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_SETTINGS = {
    "model_name": "qwen2.5:3b-instruct",
    "language": "de",
    "ollama_base_url": "http://127.0.0.1:11434",
    "tts_engine": "piper",
    "tts_model_path": "",
    "tts_voice": os.environ.get("JARVIS_TTS_VOICE", "de_DE-thorsten_emotional-medium"),
    "say_rate_wpm": os.environ.get("JARVIS_SAY_RATE_WPM", "235"),
    "tts_sir_pronunciation": os.environ.get("JARVIS_TTS_SIR_PRONUNCIATION", "Sör"),
    "whisper_model_path": "",
    "whisper_binary": "auto",
}


DEFAULT_SMARTHOME_ENTITIES = [
    {
        "id": "light.living_room",
        "entity_type": "light",
        "name": "Wohnzimmer Licht",
        "state": "off",
        "attributes": {"brightness": 0},
    },
    {
        "id": "switch.coffee_machine",
        "entity_type": "switch",
        "name": "Kaffeemaschine",
        "state": "off",
        "attributes": {},
    },
    {
        "id": "sensor.living_room_temperature",
        "entity_type": "sensor",
        "name": "Wohnzimmer Temperatur",
        "state": "21.6",
        "attributes": {"unit": "C"},
    },
]


class Database:
    def __init__(
        self,
        db_path: Path,
        project_root: Path,
        default_whisper_model: Path,
    ) -> None:
        self.db_path = db_path
        self.project_root = project_root
        self.default_whisper_model = default_whisper_model

    @asynccontextmanager
    async def _connect(self):
        connection = await aiosqlite.connect(self.db_path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON;")
        await connection.execute("PRAGMA journal_mode = WAL;")
        try:
            yield connection
        finally:
            await connection.close()

    @staticmethod
    async def _fetchall(
        connection: aiosqlite.Connection,
        query: str,
        params: tuple[Any, ...] = (),
    ) -> list[aiosqlite.Row]:
        cursor = await connection.execute(query, params)
        rows = await cursor.fetchall()
        await cursor.close()
        return rows

    @staticmethod
    async def _fetchone(
        connection: aiosqlite.Connection,
        query: str,
        params: tuple[Any, ...] = (),
    ) -> aiosqlite.Row | None:
        cursor = await connection.execute(query, params)
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def init(self) -> None:
        async with self._connect() as connection:
            await connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tool_runs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tool_input TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    success INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tool_input TEXT NOT NULL,
                    status TEXT NOT NULL,
                    decision TEXT,
                    requested_at TEXT NOT NULL,
                    decided_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS memory_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    content TEXT NOT NULL,
                    importance REAL NOT NULL DEFAULT 0.5,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS allowed_paths (
                    path TEXT PRIMARY KEY
                );

                CREATE TABLE IF NOT EXISTS smarthome_entities (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attributes TEXT NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS memory_items_fts
                USING fts5(content, content='memory_items', content_rowid='id');

                CREATE TRIGGER IF NOT EXISTS memory_items_ai AFTER INSERT ON memory_items BEGIN
                    INSERT INTO memory_items_fts(rowid, content) VALUES (new.id, new.content);
                END;

                CREATE TRIGGER IF NOT EXISTS memory_items_ad AFTER DELETE ON memory_items BEGIN
                    INSERT INTO memory_items_fts(memory_items_fts, rowid, content)
                    VALUES('delete', old.id, old.content);
                END;

                CREATE TRIGGER IF NOT EXISTS memory_items_au AFTER UPDATE ON memory_items BEGIN
                    INSERT INTO memory_items_fts(memory_items_fts, rowid, content)
                    VALUES('delete', old.id, old.content);
                    INSERT INTO memory_items_fts(rowid, content)
                    VALUES (new.id, new.content);
                END;
                """
            )

            for key, value in DEFAULT_SETTINGS.items():
                await connection.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                    (key, value),
                )

            await connection.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                ("whisper_model_path", str(self.default_whisper_model)),
            )

            await connection.execute(
                "INSERT OR IGNORE INTO allowed_paths(path) VALUES (?)",
                (str(self.project_root),),
            )

            existing_entities = await self._fetchall(
                connection,
                "SELECT id FROM smarthome_entities LIMIT 1",
            )
            if not existing_entities:
                for entity in DEFAULT_SMARTHOME_ENTITIES:
                    await connection.execute(
                        """
                        INSERT INTO smarthome_entities(id, entity_type, name, state, attributes)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            entity["id"],
                            entity["entity_type"],
                            entity["name"],
                            entity["state"],
                            json.dumps(entity["attributes"]),
                        ),
                    )

            await connection.commit()

    async def create_session(self, session_id: str) -> None:
        async with self._connect() as connection:
            await connection.execute(
                "INSERT OR IGNORE INTO sessions(id, created_at) VALUES (?, ?)",
                (session_id, utc_now_iso()),
            )
            await connection.commit()

    async def session_exists(self, session_id: str) -> bool:
        async with self._connect() as connection:
            row = await self._fetchone(
                connection,
                "SELECT id FROM sessions WHERE id = ?",
                (session_id,),
            )
            return row is not None

    async def add_message(self, session_id: str, role: str, content: str) -> int:
        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO messages(session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, utc_now_iso()),
            )
            await connection.commit()
            return int(cursor.lastrowid)

    async def list_messages(self, session_id: str, limit: int = 200) -> list[dict[str, Any]]:
        async with self._connect() as connection:
            rows = await self._fetchall(
                connection,
                """
                SELECT id, role, content, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (session_id, limit),
            )
            return [dict(row) for row in rows]

    async def list_recent_messages(self, session_id: str, limit: int = 12) -> list[dict[str, Any]]:
        async with self._connect() as connection:
            rows = await self._fetchall(
                connection,
                """
                SELECT id, role, content, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            )
            ordered = [dict(row) for row in rows]
            ordered.reverse()
            return ordered

    async def create_approval(
        self,
        approval_id: str,
        session_id: str,
        run_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        requested_at = utc_now_iso()
        async with self._connect() as connection:
            await connection.execute(
                """
                INSERT INTO approvals(
                    id, session_id, run_id, tool_name, tool_input, status, decision, requested_at
                )
                VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?)
                """,
                (
                    approval_id,
                    session_id,
                    run_id,
                    tool_name,
                    json.dumps(tool_input),
                    requested_at,
                ),
            )
            await connection.commit()

        return {
            "id": approval_id,
            "session_id": session_id,
            "run_id": run_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "status": "pending",
            "requested_at": requested_at,
        }

    async def list_pending_approvals(self) -> list[dict[str, Any]]:
        async with self._connect() as connection:
            rows = await self._fetchall(
                connection,
                """
                SELECT id, session_id, run_id, tool_name, tool_input, status, requested_at
                FROM approvals
                WHERE status = 'pending'
                ORDER BY requested_at ASC
                """
            )

        approvals: list[dict[str, Any]] = []
        for row in rows:
            parsed = dict(row)
            parsed["tool_input"] = json.loads(parsed["tool_input"])
            approvals.append(parsed)
        return approvals

    async def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        async with self._connect() as connection:
            row = await self._fetchone(
                connection,
                """
                SELECT id, session_id, run_id, tool_name, tool_input, status, decision,
                       requested_at, decided_at
                FROM approvals
                WHERE id = ?
                """,
                (approval_id,),
            )

        if row is None:
            return None

        result = dict(row)
        result["tool_input"] = json.loads(result["tool_input"])
        return result

    async def resolve_approval(
        self,
        approval_id: str,
        status: str,
        decision: str,
    ) -> None:
        async with self._connect() as connection:
            await connection.execute(
                """
                UPDATE approvals
                SET status = ?, decision = ?, decided_at = ?
                WHERE id = ?
                """,
                (status, decision, utc_now_iso(), approval_id),
            )
            await connection.commit()

    async def add_tool_run(
        self,
        run_id: str,
        session_id: str,
        tool_run_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
        success: bool,
        result: str | None,
        error: str | None,
    ) -> None:
        async with self._connect() as connection:
            await connection.execute(
                """
                INSERT INTO tool_runs(
                    id, session_id, run_id, tool_name, tool_input,
                    result, error, success, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tool_run_id,
                    session_id,
                    run_id,
                    tool_name,
                    json.dumps(tool_input),
                    result,
                    error,
                    1 if success else 0,
                    utc_now_iso(),
                ),
            )
            await connection.commit()

    async def add_memory_item(
        self,
        session_id: str,
        content: str,
        importance: float,
    ) -> None:
        async with self._connect() as connection:
            await connection.execute(
                """
                INSERT INTO memory_items(session_id, content, importance, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, content, importance, utc_now_iso()),
            )
            await connection.commit()

    async def count_messages(self, session_id: str) -> int:
        async with self._connect() as connection:
            row = await self._fetchone(
                connection,
                "SELECT COUNT(*) AS total FROM messages WHERE session_id = ?",
                (session_id,),
            )
            if row is None:
                return 0
            return int(row["total"])

    async def search_memory(self, query: str, limit: int = 4) -> list[dict[str, Any]]:
        normalized_query = " ".join(
            token.strip()
            for token in query.replace("\n", " ").split(" ")
            if token.strip() and token.strip().isalnum()
        )

        async with self._connect() as connection:
            if normalized_query:
                rows = await self._fetchall(
                    connection,
                    """
                    SELECT m.id, m.content, m.importance, m.created_at, bm25(memory_items_fts) AS rank
                    FROM memory_items_fts
                    JOIN memory_items m ON m.id = memory_items_fts.rowid
                    WHERE memory_items_fts MATCH ?
                    ORDER BY rank ASC
                    LIMIT ?
                    """,
                    (normalized_query, limit),
                )
            else:
                rows = await self._fetchall(
                    connection,
                    """
                    SELECT id, content, importance, created_at, 0.0 AS rank
                    FROM memory_items
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )

            return [dict(row) for row in rows]

    async def get_settings(self) -> dict[str, Any]:
        async with self._connect() as connection:
            settings_rows = await self._fetchall(
                connection,
                "SELECT key, value FROM settings"
            )
            allowlist_rows = await self._fetchall(
                connection,
                "SELECT path FROM allowed_paths ORDER BY path ASC"
            )

        settings = {row["key"]: row["value"] for row in settings_rows}
        settings["allowed_paths"] = [row["path"] for row in allowlist_rows]

        for key, value in DEFAULT_SETTINGS.items():
            settings.setdefault(key, value)
        settings.setdefault("whisper_model_path", str(self.default_whisper_model))

        return settings

    async def update_settings(self, update: dict[str, Any]) -> dict[str, Any]:
        async with self._connect() as connection:
            for key, value in update.items():
                if key == "allowed_paths":
                    continue
                await connection.execute(
                    "INSERT INTO settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value)),
                )

            if "allowed_paths" in update and update["allowed_paths"] is not None:
                await connection.execute("DELETE FROM allowed_paths")
                for allowed_path in update["allowed_paths"]:
                    trimmed = str(allowed_path).strip()
                    if not trimmed:
                        continue
                    await connection.execute(
                        "INSERT OR IGNORE INTO allowed_paths(path) VALUES (?)",
                        (trimmed,),
                    )

            await connection.commit()

        return await self.get_settings()

    async def list_smarthome_entities(self) -> list[dict[str, Any]]:
        async with self._connect() as connection:
            rows = await self._fetchall(
                connection,
                """
                SELECT id, entity_type, name, state, attributes
                FROM smarthome_entities
                ORDER BY id ASC
                """
            )

        entities: list[dict[str, Any]] = []
        for row in rows:
            entity = dict(row)
            entity["attributes"] = json.loads(entity["attributes"])
            entities.append(entity)
        return entities

    async def get_smarthome_entity(self, entity_id: str) -> dict[str, Any] | None:
        async with self._connect() as connection:
            row = await self._fetchone(
                connection,
                """
                SELECT id, entity_type, name, state, attributes
                FROM smarthome_entities
                WHERE id = ?
                """,
                (entity_id,),
            )

        if row is None:
            return None

        entity = dict(row)
        entity["attributes"] = json.loads(entity["attributes"])
        return entity

    async def update_smarthome_entity(
        self,
        entity_id: str,
        state: str,
        attributes: dict[str, Any],
    ) -> dict[str, Any] | None:
        async with self._connect() as connection:
            await connection.execute(
                """
                UPDATE smarthome_entities
                SET state = ?, attributes = ?
                WHERE id = ?
                """,
                (state, json.dumps(attributes), entity_id),
            )
            await connection.commit()

        return await self.get_smarthome_entity(entity_id)
