"""Readiness contracts, failure distinctions and observable read-only boundaries."""
import asyncio
import builtins
import copy
import itertools
import sqlite3
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient as RealClient

from jarvis_agent import setup_readiness as readiness
from jarvis_agent.db import Database
from jarvis_agent.setup_api import create_setup_router


@pytest.fixture
def rig(tmp_path, monkeypatch):
    settings = {"model_name": "local-chat", "ollama_base_url": "http://model-host:11434/prefix/",
                "whisper_model_path": "", "tts_engine": "piper", "tts_model_path": ""}
    calls = []
    response = {"status": 200, "json": {"models": [{"name": "local-chat:latest"}]}}

    def handle(request):
        calls.append(request)
        assert request.method == "GET"
        assert str(request.url) == "http://model-host:11434/prefix/api/tags"
        assert request.content == b""
        if "error" in response:
            raise response["error"]
        return httpx.Response(response["status"], json=response["json"])

    def client(**kwargs):
        assert kwargs == {"timeout": 3.0, "follow_redirects": False, "trust_env": False}
        return RealClient(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(readiness.httpx, "AsyncClient", client)
    monkeypatch.setattr(readiness, "find_whisper_binary", lambda *_: "/fixture/whisper-cli")
    monkeypatch.setattr(readiness, "find_system_tool", lambda *_: "/fixture/ffmpeg")
    return settings, response, calls, tmp_path / "whisper.bin"


@pytest.mark.parametrize("configured,listed,found", [
    ("local-chat", "local-chat:latest", True),
    ("local-chat:latest", "local-chat", True),
    ("team/local-chat:small", "team/local-chat:small", True),
    ("local-chat:small", "local-chat:latest", False),
    ("local-chat", "different-local-chat:latest", False),
    ("team/local-chat", "other/local-chat", False),
])
def test_exact_inventory_match_and_documented_default_tag(rig, configured, listed, found):
    settings, response, calls, default = rig
    settings["model_name"] = configured
    response["json"] = {"models": [{"name": listed}]}
    result = asyncio.run(readiness.inspect_setup(settings, default))
    assert result.chat_model.status == ("available" if found else "missing")
    assert result.state == ("degraded" if found else "needs_setup")
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [{}, {"models": None}, {"models": [None]},
                                       {"models": [{}]}, {"models": [{"name": 42}]}, []])
def test_malformed_inventory_is_error_not_missing_or_ready(rig, payload):
    settings, response, _, default = rig
    response["json"] = payload
    result = asyncio.run(readiness.inspect_setup(settings, default))
    assert result.state == "error"
    assert result.chat_model.reason == "ollama_response_invalid"


@pytest.mark.parametrize("status", [301, 401, 404, 500])
def test_http_errors_and_redirects_do_not_claim_model_absence(rig, status):
    settings, response, calls, default = rig
    response["status"] = status
    assert asyncio.run(readiness.inspect_setup(settings, default)).state == "error"
    assert len(calls) == 1


@pytest.mark.parametrize("error", [httpx.ConnectError("offline"), httpx.ReadTimeout("timeout"),
                                    TimeoutError(), httpx.RemoteProtocolError("bad protocol")])
def test_connection_failures_are_explicit(rig, error):
    settings, response, _, default = rig
    response["error"] = error
    result = asyncio.run(readiness.inspect_setup(settings, default))
    assert result.state == ("error" if isinstance(error, httpx.RemoteProtocolError) else "needs_setup")


def test_empty_inventory_and_unconfigured_model(rig):
    settings, response, calls, default = rig
    response["json"] = {"models": []}
    assert asyncio.run(readiness.inspect_setup(settings, default)).chat_model.reason == "chat_model_missing"
    settings["model_name"] = ""
    assert asyncio.run(readiness.inspect_setup(settings, default)).chat_model.reason == "chat_model_not_configured"
    assert len(calls) == 1


@pytest.mark.parametrize("endpoint", ["", "file:///tmp/model", "not-a-url", "http://[bad"])
def test_invalid_endpoint_never_issues_request(rig, endpoint):
    settings, _, calls, default = rig
    settings["ollama_base_url"] = endpoint
    result = asyncio.run(readiness.inspect_setup(settings, default))
    assert result.state == "error"
    assert not calls


def test_stt_default_and_configured_path_and_conservative_voice(rig, tmp_path):
    settings, _, _, default = rig
    default.write_bytes(b"fixture only; not a functional model")
    assert asyncio.run(readiness.inspect_setup(settings, default)).stt.status == "available"
    settings["whisper_model_path"] = str(tmp_path / "missing.bin")
    assert asyncio.run(readiness.inspect_setup(settings, default)).stt.status == "missing"
    settings["tts_model_path"] = str(default)
    result = asyncio.run(readiness.inspect_setup(settings, default))
    assert result.tts.status == "unknown"
    assert result.tts.reason == "voice_unverified"
    settings["tts_engine"] = "say"
    assert asyncio.run(readiness.inspect_setup(settings, default)).tts.status == "unknown"


def test_stt_is_missing_when_model_exists_but_whisper_cli_does_not(rig, monkeypatch):
    settings, _, _, default = rig
    default.write_bytes(b"fixture only; not a functional model")
    monkeypatch.setattr(readiness, "find_whisper_binary", lambda *_: None)
    result = asyncio.run(readiness.inspect_setup(settings, default))
    assert result.stt.status == "missing"
    assert result.stt.reason == "whisper_cli_missing"


def test_stt_is_missing_when_ffmpeg_unavailable_despite_model_and_binary(rig, monkeypatch):
    settings, _, _, default = rig
    default.write_bytes(b"model fixture")
    monkeypatch.setattr(readiness, "find_system_tool", lambda *_: None)
    result = asyncio.run(readiness.inspect_setup(settings, default))
    assert result.stt.status == "missing"
    assert result.stt.reason == "ffmpeg_missing"
    assert result.state == "degraded"


def test_directory_empty_and_unreadable_files_are_not_available(tmp_path, monkeypatch):
    assert readiness.inspect_model_file(tmp_path).status == "missing"
    empty = tmp_path / "empty.bin"
    empty.touch()
    assert readiness.inspect_model_file(empty).status == "missing"
    def denied(*args, **kwargs):
        raise PermissionError("not readable")
    with monkeypatch.context() as patches:
        patches.setattr(Path, "stat", denied)
        assert readiness.inspect_model_file(empty).status == "unknown"


@pytest.mark.parametrize("chat,stt,tts", itertools.product(
    ["available", "missing", "unreachable", "unknown", "error"], repeat=3))
def test_state_matrix_is_deterministic(chat, stt, tts):
    values = [readiness.ComponentStatus(status=status, reason="test") for status in (chat, stt, tts)]
    expected = ("error" if chat in {"error", "unknown"} else "needs_setup" if chat != "available"
                else "degraded" if stt != "available" or tts != "available" else "ready")
    assert readiness.combine_status(*values).state == expected
    assert readiness.combine_status(*values) == readiness.combine_status(*values)


def test_inspection_has_no_process_file_or_settings_side_effects(rig, monkeypatch, tmp_path):
    settings, _, calls, default = rig
    before = copy.deepcopy(settings)
    paths_before = set(tmp_path.rglob("*"))
    original_open = builtins.open
    def no_side_effect(*args, **kwargs):
        raise AssertionError("Setup attempted a side effect")
    def read_only_open(file, mode="r", *args, **kwargs):
        assert not any(flag in mode for flag in "wax+")
        return original_open(file, mode, *args, **kwargs)
    with monkeypatch.context() as patches:
        for name in ("run", "Popen", "call", "check_call", "check_output"):
            patches.setattr(subprocess, name, no_side_effect)
        patches.setattr(asyncio, "create_subprocess_exec", no_side_effect)
        patches.setattr(asyncio, "create_subprocess_shell", no_side_effect)
        patches.setattr(builtins, "open", read_only_open)
        for name in ("write_text", "write_bytes", "mkdir", "touch", "unlink", "rename"):
            patches.setattr(Path, name, no_side_effect)
        result = asyncio.run(readiness.inspect_setup(settings, default))
    assert result.state == "degraded"
    assert settings == before
    assert set(tmp_path.rglob("*")) == paths_before
    assert [request.method for request in calls] == ["GET"]


def test_endpoint_reads_real_settings_without_database_mutations(rig, tmp_path):
    settings, _, calls, default = rig
    database = Database(tmp_path / "setup.db", tmp_path, default)
    async def prepare():
        await database.init()
        await database.update_settings(settings)
        await database.create_session("existing-session")
    asyncio.run(prepare())
    def dump():
        with sqlite3.connect(database.db_path) as connection:
            return list(connection.iterdump())
    before = dump()
    app = FastAPI()
    app.include_router(create_setup_router(database.get_settings, default))
    async def exercise():
        async with RealClient(transport=httpx.ASGITransport(app=app), base_url="http://agent") as client:
            first = await client.get("/v1/setup/status")
            second = await client.get("/v1/setup/status")
            assert first.status_code == 200
            assert first.headers["cache-control"] == "no-store"
            assert first.json() == second.json()
            assert first.json()["state"] == "degraded"
            assert (await client.post("/v1/setup/status")).status_code == 405
    asyncio.run(exercise())
    assert dump() == before
    assert len(calls) == 2
