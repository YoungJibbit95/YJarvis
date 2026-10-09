from __future__ import annotations

import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from .persistence import migrate_database


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_learned_trigger(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return collapsed.strip(" ,.:;!?")


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
        # Validate/adopt before WAL configuration or legacy default seeding.
        # The worker owns its SQLite connection and the complete transaction.
        await asyncio.to_thread(migrate_database, self.db_path)
        async with self._connect() as connection:
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

    async def upsert_learned_command(
        self,
        *,
        trigger: str,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_trigger = normalize_learned_trigger(trigger)
        if not normalized_trigger:
            raise ValueError("trigger darf nicht leer sein")

        created_or_updated_at = utc_now_iso()
        async with self._connect() as connection:
            await connection.execute(
                """
                INSERT INTO learned_commands(
                    trigger, tool_name, tool_input, created_at, updated_at, enabled
                )
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(trigger) DO UPDATE SET
                    tool_name = excluded.tool_name,
                    tool_input = excluded.tool_input,
                    updated_at = excluded.updated_at,
                    enabled = 1
                """,
                (
                    normalized_trigger,
                    tool_name,
                    json.dumps(tool_input),
                    created_or_updated_at,
                    created_or_updated_at,
                ),
            )
            await connection.commit()

        command = await self.get_learned_command(normalized_trigger)
        if command is None:
            raise ValueError("gelernter Befehl konnte nicht gespeichert werden")
        return command

    async def get_learned_command(self, trigger: str) -> dict[str, Any] | None:
        normalized_trigger = normalize_learned_trigger(trigger)
        if not normalized_trigger:
            return None

        async with self._connect() as connection:
            row = await self._fetchone(
                connection,
                """
                SELECT trigger, tool_name, tool_input, created_at, updated_at,
                       enabled, usage_count, success_count, failure_count
                FROM learned_commands
                WHERE trigger = ?
                """,
                (normalized_trigger,),
            )

        if row is None:
            return None

        parsed = dict(row)
        parsed["tool_input"] = json.loads(parsed["tool_input"])
        parsed["enabled"] = bool(parsed["enabled"])
        return parsed

    async def find_matching_learned_command(self, user_message: str) -> dict[str, Any] | None:
        normalized_message = normalize_learned_trigger(user_message)
        if not normalized_message:
            return None

        async with self._connect() as connection:
            rows = await self._fetchall(
                connection,
                """
                SELECT trigger, tool_name, tool_input, created_at, updated_at,
                       enabled, usage_count, success_count, failure_count
                FROM learned_commands
                WHERE enabled = 1
                ORDER BY LENGTH(trigger) DESC, updated_at DESC
                LIMIT 200
                """,
            )

        for row in rows:
            trigger = str(row["trigger"]).strip()
            if not trigger:
                continue

            if normalized_message == trigger or normalized_message.startswith(f"{trigger} "):
                parsed = dict(row)
                parsed["tool_input"] = json.loads(parsed["tool_input"])
                parsed["enabled"] = bool(parsed["enabled"])
                return parsed

        return None

    async def list_learned_commands(self, limit: int = 40) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 200))
        async with self._connect() as connection:
            rows = await self._fetchall(
                connection,
                """
                SELECT trigger, tool_name, tool_input, created_at, updated_at,
                       enabled, usage_count, success_count, failure_count
                FROM learned_commands
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            )

        commands: list[dict[str, Any]] = []
        for row in rows:
            parsed = dict(row)
            parsed["tool_input"] = json.loads(parsed["tool_input"])
            parsed["enabled"] = bool(parsed["enabled"])
            commands.append(parsed)
        return commands

    async def delete_learned_command(self, trigger: str) -> bool:
        normalized_trigger = normalize_learned_trigger(trigger)
        if not normalized_trigger:
            return False

        async with self._connect() as connection:
            cursor = await connection.execute(
                "DELETE FROM learned_commands WHERE trigger = ?",
                (normalized_trigger,),
            )
            await connection.commit()
            deleted = cursor.rowcount > 0
            await cursor.close()
        return deleted

    async def record_learned_command_result(self, trigger: str, success: bool) -> None:
        normalized_trigger = normalize_learned_trigger(trigger)
        if not normalized_trigger:
            return

        success_delta = 1 if success else 0
        failure_delta = 0 if success else 1

        async with self._connect() as connection:
            await connection.execute(
                """
                UPDATE learned_commands
                SET usage_count = usage_count + 1,
                    success_count = success_count + ?,
                    failure_count = failure_count + ?,
                    updated_at = ?
                WHERE trigger = ?
                """,
                (success_delta, failure_delta, utc_now_iso(), normalized_trigger),
            )
            await connection.commit()

    async def record_tool_learning(
        self,
        *,
        tool_name: str,
        success: bool,
        latency_ms: int,
    ) -> None:
        normalized_tool_name = str(tool_name or "").strip()
        if not normalized_tool_name:
            return

        normalized_latency = max(0, int(latency_ms))

        async with self._connect() as connection:
            row = await self._fetchone(
                connection,
                """
                SELECT success_count, failure_count, average_latency_ms
                FROM tool_learning_stats
                WHERE tool_name = ?
                """,
                (normalized_tool_name,),
            )

            current_success = 0
            current_failure = 0
            current_average = 0.0
            if row is not None:
                current_success = int(row["success_count"])
                current_failure = int(row["failure_count"])
                current_average = float(row["average_latency_ms"])

            total_runs = current_success + current_failure
            new_average = (
                ((current_average * total_runs) + normalized_latency) / float(total_runs + 1)
                if total_runs >= 0
                else float(normalized_latency)
            )

            success_delta = 1 if success else 0
            failure_delta = 0 if success else 1
            now = utc_now_iso()

            await connection.execute(
                """
                INSERT INTO tool_learning_stats(
                    tool_name,
                    success_count,
                    failure_count,
                    average_latency_ms,
                    last_latency_ms,
                    last_used_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(tool_name) DO UPDATE SET
                    success_count = excluded.success_count,
                    failure_count = excluded.failure_count,
                    average_latency_ms = excluded.average_latency_ms,
                    last_latency_ms = excluded.last_latency_ms,
                    last_used_at = excluded.last_used_at
                """,
                (
                    normalized_tool_name,
                    current_success + success_delta,
                    current_failure + failure_delta,
                    new_average,
                    normalized_latency,
                    now,
                ),
            )
            await connection.commit()

    async def get_tool_learning_stats(
        self,
        *,
        tool_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        async with self._connect() as connection:
            if tool_names:
                cleaned = [str(item).strip() for item in tool_names if str(item).strip()]
                if not cleaned:
                    return []
                placeholders = ",".join("?" for _ in cleaned)
                rows = await self._fetchall(
                    connection,
                    f"""
                    SELECT tool_name, success_count, failure_count,
                           average_latency_ms, last_latency_ms, last_used_at
                    FROM tool_learning_stats
                    WHERE tool_name IN ({placeholders})
                    """,
                    tuple(cleaned),
                )
            else:
                rows = await self._fetchall(
                    connection,
                    """
                    SELECT tool_name, success_count, failure_count,
                           average_latency_ms, last_latency_ms, last_used_at
                    FROM tool_learning_stats
                    ORDER BY (success_count + failure_count) DESC, tool_name ASC
                    LIMIT 200
                    """,
                )

        return [dict(row) for row in rows]

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

    async def search_memory(self, query: str, limit: int = 4, *, session_id: str | None = None) -> list[dict[str, Any]]:
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
                      AND (? IS NULL OR m.session_id = ?)
                    ORDER BY rank ASC
                    LIMIT ?
                    """,
                    (normalized_query, session_id, session_id, limit),
                )
            else:
                rows = await self._fetchall(
                    connection,
                    """
                    SELECT id, content, importance, created_at, 0.0 AS rank
                    FROM memory_items
                    WHERE (? IS NULL OR session_id = ?)
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (session_id, session_id, limit),
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

    async def update_settings_if_current(self, update: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
        """Atomically reject stale setup writes; no allowlist or schema change."""
        if set(update) - {"model_name", "tts_engine", "tts_model_path", "tts_voice", "whisper_model_path", "whisper_binary"}:
            raise ValueError("Unsupported setup settings")
        async with self._connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            try:
                current = await self.get_settings()
                if any(current.get(key) != expected.get(key) for key in update):
                    raise ValueError("Einstellungen wurden inzwischen geändert. Bitte Einrichtung erneut starten.")
                for key, value in update.items():
                    await connection.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
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