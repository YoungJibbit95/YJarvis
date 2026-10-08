import asyncio
import builtins
import ctypes
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

from fastapi import FastAPI
import httpx
from pydantic import ValidationError
import pytest

from jarvis_agent import setup_api, setup_hardware as hardware
from jarvis_agent.db import Database
from jarvis_agent.hardware_profile import HardwareProfile


def profile(**changes):
    return dict(platform="windows", architecture="x86_64", logical_cpu_count=12,
                total_memory_bytes=32 * 1024**3, available_storage_bytes=0,
                storage_path_scope="app_runtime_directory") | changes


@pytest.mark.parametrize("field,value", [
    ("platform", "freebsd"), ("architecture", "AMD64"), ("logical_cpu_count", 0),
    ("logical_cpu_count", True), ("logical_cpu_count", "12"), ("total_memory_bytes", 0),
    ("total_memory_bytes", -1), ("total_memory_bytes", 2**53), ("available_storage_bytes", -1),
    ("available_storage_bytes", 1.5), ("storage_path_scope", "model_install_directory"), ("gpu", "fast"),
])
def test_profile_rejects_invalid_metadata(field, value):
    with pytest.raises(ValidationError):
        HardwareProfile(**profile(**{field: value}))


def test_profile_is_frozen_and_unknown_is_not_zero():
    value = HardwareProfile(**profile(logical_cpu_count=None, total_memory_bytes=None, available_storage_bytes=None))
    assert value.model_dump()["total_memory_bytes"] is None
    with pytest.raises(ValidationError):
        value.logical_cpu_count = 5
    assert HardwareProfile(**profile()).available_storage_bytes == 0  # A full filesystem is known.


@pytest.mark.parametrize("raw,expected", [("win32", "windows"), ("darwin", "macos"), ("linux", "linux"), ("freebsd", "unknown")])
def test_normalized_platform(monkeypatch, raw, expected):
    monkeypatch.setattr(hardware, "sys", SimpleNamespace(platform=raw))
    assert hardware._platform() == expected


@pytest.mark.parametrize("raw,expected", [("x86_64", "x86_64"), ("AMD64", "x86_64"), ("aarch64", "arm64"), ("arm64", "arm64"), ("riscv64", "other"), ("", "unknown")])
def test_posix_architecture(monkeypatch, raw, expected):
    monkeypatch.setattr(hardware.os, "uname", lambda: SimpleNamespace(machine=raw), raising=False)
    assert hardware._architecture("linux") == expected
    assert hardware._architecture("macos") == expected


@pytest.mark.parametrize("machine,success,expected", [(0x8664, 1, "x86_64"), (0xAA64, 1, "arm64"), (0x14C, 1, "other"), (0, 0, "unknown")])
def test_windows_native_architecture(monkeypatch, machine, success, expected):
    def current():
        return 123
    def query(handle, process, native):
        assert handle == 123
        native._obj.value = machine
        return success
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: SimpleNamespace(GetCurrentProcess=current, IsWow64Process2=query), raising=False)
    assert hardware._architecture("windows") == expected
    assert query.restype is ctypes.c_int


@pytest.mark.parametrize("success,expected", [(1, 32 * 1024**3), (0, None)])
def test_windows_physical_memory_abi(monkeypatch, success, expected):
    def query(pointer):
        assert pointer._obj.length == 64
        pointer._obj.total_physical = 32 * 1024**3
        pointer._obj.available_physical = 1024  # Never substitute free RAM for total.
        return success
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: SimpleNamespace(GlobalMemoryStatusEx=query), raising=False)
    assert hardware._total_memory("windows") == expected


@pytest.mark.parametrize("pages,size,expected", [(1024, 4096, 4194304), (-1, 4096, None), (1024, 0, None), (2**52, 4096, None)])
def test_linux_physical_pages(monkeypatch, pages, size, expected):
    monkeypatch.setattr(hardware.os, "sysconf", lambda name: {"SC_PHYS_PAGES": pages, "SC_PAGE_SIZE": size}[name], raising=False)
    assert hardware._total_memory("linux") == expected


@pytest.mark.parametrize("result,size,expected", [(0, 8, 16 * 1024**3), (-1, 8, None), (0, 4, None)])
def test_macos_sysctl_is_read_only_with_uint64_buffer(monkeypatch, result, size, expected):
    def query(name, output, length, new_value, new_length):
        assert name == b"hw.memsize" and length._obj.value == 8
        assert new_value is None and new_length == 0
        output._obj.value = 16 * 1024**3
        length._obj.value = size
        return result
    def load(name):
        assert name == "/usr/lib/libSystem.B.dylib"
        return SimpleNamespace(sysctlbyname=query)
    monkeypatch.setattr(ctypes, "CDLL", load)
    assert hardware._total_memory("macos") == expected


def test_independent_unknown_probes(monkeypatch, tmp_path):
    def unavailable(*args, **kwargs):
        raise OSError("unavailable")
    monkeypatch.setattr(hardware.os, "cpu_count", unavailable)
    monkeypatch.setattr(hardware.os, "uname", unavailable, raising=False)
    monkeypatch.setattr(hardware.os, "sysconf", unavailable, raising=False)
    monkeypatch.setattr(ctypes, "WinDLL", unavailable, raising=False)
    monkeypatch.setattr(ctypes, "CDLL", unavailable)
    for host in ("windows", "macos", "linux", "unknown"):
        assert hardware._total_memory(host) is None
        assert hardware._architecture(host) == "unknown"
    monkeypatch.setattr(hardware, "_platform", lambda: "linux")
    value = hardware.inspect_hardware(tmp_path)
    assert value.logical_cpu_count is None and value.total_memory_bytes is None
    assert value.available_storage_bytes is not None  # Failed probes do not erase others.


def test_storage_measures_exact_existing_scope_without_creation(monkeypatch, tmp_path):
    seen = []
    def usage(path):
        seen.append(path)
        return SimpleNamespace(free=0)
    monkeypatch.setattr(hardware.shutil, "disk_usage", usage)
    assert hardware._available_storage(tmp_path, "linux") == 0
    assert seen == [tmp_path]
    for path in (None, Path("relative"), tmp_path / "missing", tmp_path / "missing" / "models"):
        assert hardware._available_storage(path, "linux") is None
    assert seen == [tmp_path] and not (tmp_path / "missing").exists()
    (tmp_path / "file").write_text("not a directory")
    assert hardware._available_storage(tmp_path / "file", "linux") is None
    monkeypatch.setattr(hardware.shutil, "disk_usage", lambda p: (_ for _ in ()).throw(PermissionError()))
    assert hardware._available_storage(tmp_path, "linux") is None


def test_windows_nonfixed_storage_is_unknown_before_filesystem_probe(monkeypatch, tmp_path):
    def query(root):
        return 4  # DRIVE_REMOTE
    def forbidden(*args):
        raise AssertionError("Remote storage was inspected")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: SimpleNamespace(GetDriveTypeW=query), raising=False)
    monkeypatch.setattr(hardware.shutil, "disk_usage", forbidden)
    monkeypatch.setattr(Path, "is_dir", forbidden)
    assert hardware._available_storage(tmp_path, "windows") is None
    assert hardware._available_storage(Path("//server/share"), "windows") is None


@pytest.mark.skipif(sys.platform not in ("win32", "linux"), reason="Real Windows/Linux CI smoke; macOS requires its own host")
def test_real_host_baseline(tmp_path):
    value = hardware.inspect_hardware(tmp_path)
    assert value.platform in ("windows", "linux")
    assert value.architecture in ("x86_64", "arm64", "other")
    assert value.logical_cpu_count > 0
    assert value.total_memory_bytes > 0
    assert value.available_storage_bytes >= 0


def test_endpoint_does_not_mutate_or_invoke_catalog_readiness_network_processes(tmp_path, monkeypatch):
    database = Database(tmp_path / "hardware.db", tmp_path, tmp_path / "missing.bin")
    asyncio.run(database.init())
    settings = asyncio.run(database.get_settings())
    with sqlite3.connect(database.db_path) as connection:
        before = list(connection.iterdump())
    attempts = []
    def deny(*args, **kwargs):
        attempts.append("forbidden boundary")
        raise AssertionError(attempts[-1])
    app = FastAPI()
    app.include_router(setup_api.create_setup_router(deny, tmp_path / "missing.bin", tmp_path))
    original_open = builtins.open
    def read_only_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in "wax+"):
            return deny()
        return original_open(file, mode, *args, **kwargs)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            with monkeypatch.context() as patches:
                patches.setattr(setup_api, "inspect_setup", deny)
                patches.setattr(builtins, "open", read_only_open)
                patches.setattr(socket, "getaddrinfo", deny)
                patches.setattr(socket.socket, "connect", deny)
                patches.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny)
                patches.setattr(subprocess, "Popen", deny)
                patches.setattr(hardware.os, "system", deny)
                patches.setattr(asyncio, "create_subprocess_exec", deny)
                patches.setattr(asyncio, "create_subprocess_shell", deny)
                for name in ("mkdir", "write_text", "write_bytes", "touch", "unlink", "rename"):
                    patches.setattr(Path, name, deny)
                for _ in range(2):
                    response = await client.get("/v1/setup/hardware")
                    assert response.status_code == 200
                    assert response.headers["cache-control"] == "no-store"
                    value = HardwareProfile.model_validate(response.json())
                    assert value.storage_path_scope == "app_runtime_directory"
                patches.setattr(setup_api, "inspect_hardware", deny)
                for method in ("POST", "PUT", "PATCH", "DELETE", "HEAD"):
                    assert (await client.request(method, "/v1/setup/hardware")).status_code == 405
                catalog = await client.get("/v1/setup/models")
                assert catalog.json() == setup_api.BUNDLED_MODEL_CATALOG.model_dump(mode="json")
    asyncio.run(exercise())
    assert not attempts
    assert asyncio.run(database.get_settings()) == settings
    with sqlite3.connect(database.db_path) as connection:
        assert list(connection.iterdump()) == before
