from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class EventBus:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[session_id].add(websocket)

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            session_connections = self._connections.get(session_id)
            if not session_connections:
                return
            session_connections.discard(websocket)
            if not session_connections:
                self._connections.pop(session_id, None)

    async def publish(self, session_id: str, event: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._connections.get(session_id, set()))

        dead_connections: list[WebSocket] = []

        for connection in targets:
            try:
                await connection.send_json(event)
            except Exception:
                dead_connections.append(connection)

        if dead_connections:
            async with self._lock:
                current = self._connections.get(session_id)
                if not current:
                    return
                for websocket in dead_connections:
                    current.discard(websocket)
                if not current:
                    self._connections.pop(session_id, None)
