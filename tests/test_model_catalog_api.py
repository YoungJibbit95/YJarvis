"""The catalog route is pure transport; even unsupported methods cannot mutate."""
import asyncio
import copy
from pathlib import Path
import socket
import sqlite3
import subprocess

from fastapi import FastAPI
import httpx

from jarvis_agent.bundled_model_catalog import BUNDLED_MODEL_CATALOG
from jarvis_agent.db import Database
from jarvis_agent import setup_api


def test_catalog_endpoint_is_exact_offline_and_read_only(tmp_path, monkeypatch):
    database = Database(tmp_path / "catalog.db", tmp_path, tmp_path / "missing.bin")
    asyncio.run(database.init())
    settings = asyncio.run(database.get_settings())
    original_settings = copy.deepcopy(settings)
    with sqlite3.connect(database.db_path) as connection:
        before = list(connection.iterdump())
    attempts = []
    def deny(*args, **kwargs):
        attempts.append("side effect or settings/readiness access")
        raise AssertionError(attempts[-1])
    app = FastAPI()
    app.include_router(setup_api.create_setup_router(deny, tmp_path / "missing.bin"))
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            with monkeypatch.context() as patches:
                patches.setattr(setup_api, "inspect_setup", deny)
                patches.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny)
                patches.setattr(socket, "getaddrinfo", deny)
                patches.setattr(socket.socket, "connect", deny)
                patches.setattr(subprocess, "Popen", deny)
                patches.setattr(asyncio, "create_subprocess_exec", deny)
                patches.setattr(asyncio, "create_subprocess_shell", deny)
                for name in ("mkdir", "write_text", "write_bytes", "touch", "unlink", "rename"):
                    patches.setattr(Path, name, deny)
                for _ in range(2):
                    response = await client.get("/v1/setup/models")
                    assert response.status_code == 200
                    assert response.json() == BUNDLED_MODEL_CATALOG.model_dump(mode="json")
                    assert len(response.json()["entries"]) == 3
                for method in ("POST", "PUT", "PATCH", "DELETE", "HEAD"):
                    response = await client.request(method, "/v1/setup/models")
                    assert response.status_code == 405
    asyncio.run(exercise())
    assert not attempts
    assert asyncio.run(database.get_settings()) == original_settings
    with sqlite3.connect(database.db_path) as connection:
        assert list(connection.iterdump()) == before
