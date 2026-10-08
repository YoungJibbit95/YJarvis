"""Catalog integrity, offline use and separation from real local readiness."""
import asyncio
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import httpx
import pytest
from pydantic import ValidationError

from jarvis_agent.bundled_model_catalog import BUNDLED_MODEL_CATALOG as catalog
from jarvis_agent.model_catalog import ModelCatalog, ModelCatalogEntry
from jarvis_agent import setup_readiness


def test_bundled_entries_are_unique_and_round_trip_without_losing_unknowns():
    assert len(catalog.entries) == 3
    assert {entry.category for entry in catalog.entries} == {"chat", "speech_to_text", "text_to_speech"}
    assert len({entry.id for entry in catalog.entries}) == 3
    assert len({(entry.runtime.backend, entry.runtime.model_id) for entry in catalog.entries}) == 3
    assert ModelCatalog.model_validate_json(catalog.model_dump_json()) == catalog
    voice = catalog.get("piper-de-thorsten-medium")
    assert voice.licenses[0].scope == "model" and voice.licenses[0].name is None
    assert voice.licenses[1].scope == "dataset" and voice.licenses[1].name == "CC0"
    assert voice.acquisition.approximate_download_bytes is None
    assert voice.context_window_tokens is None


@pytest.mark.parametrize("duplicate", ["id", "runtime"])
def test_duplicate_identifiers_fail(duplicate):
    entry = catalog.entries[0].model_dump()
    other = copy.deepcopy(entry)
    if duplicate == "id":
        other["runtime"]["model_id"] = "different:tag"
    else:
        other["id"] = "different-id"
    with pytest.raises(ValidationError, match="Duplicate"):
        ModelCatalog(entries=(entry, other))


@pytest.mark.parametrize("path,value", [
    (("id",), "Bad ID"),
    (("category",), "image"),
    (("display_name",), " "),
    (("publisher",), ""),
    (("model_id",), 123),
    (("description",), ""),
    (("runtime", "backend"), "unknown"),
    (("runtime", "model_id"), ""),
    (("runtime", "backend"), "piper"),
    (("category",), "speech_to_text"),
    (("acquisition", "mechanism"), "shell"),
    (("acquisition", "mechanism"), "hugging_face_files"),
    (("acquisition", "source", "url"), "https://example.org/model"),
    (("source", "url"), "not-a-url"),
    (("source", "url"), "http://huggingface.co/Qwen/model"),
    (("source", "url"), "https://user:password@huggingface.co/model"),
    (("source", "url"), "https://huggingface.co/model?token=secret"),
    (("source", "url"), "https://huggingface.co/model#fragment"),
    (("source", "publisher"), ""),
    (("source", "checked_on"), "not-a-date"),
    (("context_window_tokens",), 0),
    (("context_window_tokens",), "32768"),
    (("context_window_tokens",), True),
    (("acquisition", "approximate_download_bytes"), -1),
    (("acquisition", "approximate_download_bytes"), 1.5),
    (("acquisition", "approximate_download_bytes"), True),
    (("licenses",), ()),
    (("recommended",), True),
    (("runtime", "command"), "ollama pull anything"),
    (("acquisition", "install_path"), "somewhere"),
    (("source", "download"), True),
])
def test_unknown_or_invalid_entry_data_fails(path, value):
    data = catalog.entries[0].model_dump()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        ModelCatalogEntry.model_validate(data)


def test_license_scopes_and_non_chat_context_are_checked():
    data = catalog.get("piper-de-thorsten-medium").model_dump()
    for licenses in (data["licenses"][1:], (data["licenses"][0],) * 2):
        with pytest.raises(ValidationError, match="license"):
            ModelCatalogEntry.model_validate({**data, "licenses": licenses})
    with pytest.raises(ValidationError):
        ModelCatalogEntry.model_validate({**data, "context_window_tokens": 32768})
    with pytest.raises(ValidationError):
        ModelCatalog(entries=())


@pytest.mark.parametrize("catalog_id", ["unknown", "QWEN25-3B-INSTRUCT-OLLAMA", "qwen2.5:3b-instruct", "https://example.org/model"])
def test_lookup_does_not_guess_or_accept_urls(catalog_id):
    with pytest.raises(KeyError):
        catalog.get(catalog_id)


def test_catalog_and_nested_metadata_cannot_be_mutated():
    entry = catalog.entries[0]
    for target, field, value in (
        (catalog, "entries", ()), (entry, "description", "changed"),
        (entry.runtime, "model_id", "changed"), (entry.source, "publisher", "changed"),
        (entry.licenses[0], "name", "changed"), (entry.acquisition, "mechanism", "changed"),
    ):
        with pytest.raises(ValidationError, match="frozen"):
            setattr(target, field, value)
    exported = json.loads(catalog.model_dump_json())
    exported["entries"][0]["runtime"]["model_id"] = "changed"
    assert catalog.entries[0].runtime.model_id == "qwen2.5:3b-instruct"


def test_cold_import_lookup_and_serialization_are_offline_and_inert(tmp_path):
    # Fresh interpreter; record attempts so swallowed exceptions still fail.
    script = textwrap.dedent('''
        import builtins, io, os, pathlib, socket, subprocess, sys
        from contextlib import ExitStack
        from unittest.mock import patch
        attempts = []
        def deny(*args, **kwargs):
            attempts.append("side effect")
            raise AssertionError("Catalog attempted a side effect")
        def read_only(original):
            def guarded(file, mode="r", *args, **kwargs):
                if any(flag in mode for flag in "wax+"):
                    return deny()
                return original(file, mode, *args, **kwargs)
            return guarded
        real_os_open = os.open
        def read_only_os_open(path, flags, *args, **kwargs):
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                return deny()
            return real_os_open(path, flags, *args, **kwargs)
        with ExitStack() as guards:
            guards.enter_context(patch.object(builtins, "open", read_only(builtins.open)))
            guards.enter_context(patch.object(io, "open", read_only(io.open)))
            guards.enter_context(patch.object(os, "open", read_only_os_open))
            for module, names in (
                (os, ("system", "mkdir", "makedirs", "remove", "unlink", "rmdir", "rename", "replace")),
                (subprocess, ("Popen", "run", "call", "check_call", "check_output")),
                (socket, ("getaddrinfo", "create_connection")),
                (socket.socket, ("connect", "connect_ex", "sendto", "sendall", "send")),
                (pathlib.Path, ("mkdir", "touch", "write_bytes", "write_text", "unlink", "rename", "replace")),
            ):
                for name in names:
                    guards.enter_context(patch.object(module, name, deny))
            from jarvis_agent.bundled_model_catalog import BUNDLED_MODEL_CATALOG as catalog
            for entry in catalog.entries:
                assert catalog.get(entry.id) == entry
            payload = catalog.model_dump_json()
            assert type(catalog).model_validate_json(payload) == catalog
        assert not attempts, attempts
        assert not any(name in sys.modules for name in (
            "jarvis_agent.config", "jarvis_agent.db", "jarvis_agent.audio",
            "jarvis_agent.main", "jarvis_agent.setup_readiness",
        ))
        print("offline catalog: 3 entries; zero side effects")
    ''')
    agent_path = Path(__file__).resolve().parents[1] / "apps" / "agent"
    result = subprocess.run(
        [sys.executable, "-B", "-c", script], cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(agent_path)},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "offline catalog: 3 entries; zero side effects"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("installed", [False, True])
def test_catalog_presence_never_substitutes_for_readiness(installed, tmp_path, monkeypatch):
    settings = {"model_name": "qwen2.5:3b-instruct", "ollama_base_url": "http://local:11434",
                "tts_engine": "piper", "tts_model_path": ""}
    original = copy.deepcopy(settings)
    calls = []
    real_client = httpx.AsyncClient
    def inventory(request):
        calls.append(request)
        return httpx.Response(200, json={"models": [{"name": settings["model_name"]}] if installed else []})
    monkeypatch.setattr(setup_readiness.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(inventory), **kwargs))
    before = asyncio.run(setup_readiness.inspect_setup(settings, tmp_path / "missing.bin"))
    for entry in catalog.entries:
        catalog.get(entry.id).model_dump_json()
    after = asyncio.run(setup_readiness.inspect_setup(settings, tmp_path / "missing.bin"))
    assert before == after
    assert after.state == ("degraded" if installed else "needs_setup")
    assert after.stt.status == "missing" and after.tts.status == "missing"
    assert settings == original
    assert len(calls) == 2 and all(request.method == "GET" for request in calls)
    assert list(tmp_path.iterdir()) == []
