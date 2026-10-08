import asyncio
import builtins
import ctypes as ct
import os
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

from jarvis_agent import setup_accelerators as probe, setup_api
from jarvis_agent.accelerator_profile import AcceleratorAdapter, AcceleratorProfile
from jarvis_agent.db import Database


def adapter(**changes):
    return dict(display_name="Test adapter", dedicated_video_memory_bytes=0,
                shared_system_memory_bytes=None, classification="hardware") | changes


@pytest.mark.parametrize("field,value", [
    ("display_name", ""), ("display_name", "  "), ("display_name", "x" * 129),
    ("display_name", 123), ("classification", "NVIDIA"), ("vendor", "guessed"),
] + [(field, value) for field in ("dedicated_video_memory_bytes", "shared_system_memory_bytes")
     for value in (-1, 2**53, True, "8", 1.5)])
def test_adapter_contract_rejects_invalid_values(field, value):
    with pytest.raises(ValidationError):
        AcceleratorAdapter(**adapter(**{field: value}))


def test_contract_is_strict_frozen_bounded_and_unknown_is_not_zero():
    item = AcceleratorAdapter(**adapter(shared_system_memory_bytes=2**53 - 1))
    value = AcceleratorProfile(status="available", adapters=(item,))
    assert item.dedicated_video_memory_bytes == 0
    assert AcceleratorAdapter(**adapter()).shared_system_memory_bytes is None
    for target, field, replacement in ((item, "display_name", "changed"), (value, "adapters", ())):
        with pytest.raises(ValidationError):
            setattr(target, field, replacement)
    for changes in ({"adapters": [item]}, {"adapters": (item,) * 65}, {"status": "fast"},
                    {"status": "unknown"}, {"status": "unsupported"}, {"score": 5}):
        with pytest.raises(ValidationError):
            AcceleratorProfile(**(dict(status="available", adapters=(item,)) | changes))
    for status in ("available", "unknown", "unsupported"):
        assert AcceleratorProfile(status=status, adapters=()).adapters == ()
    assert AcceleratorProfile.model_validate_json(value.model_dump_json()) == value


def descriptor(name="Test adapter", dedicated=8 * 1024**3, shared=16 * 1024**3, flags=0):
    desc = probe._AdapterDesc1()
    encoded = name.encode("utf-16-le")
    ct.memmove(desc.description, encoded, len(encoded))
    desc.dedicated_video_memory = dedicated
    desc.dedicated_system_memory = 123456  # Must not be folded into either exposed field.
    desc.shared_system_memory = shared
    desc.flags = flags
    return desc


class FakeDXGI:
    """Real ctypes vtables/callbacks: exercise dispatch, pointers and HRESULT ABI."""
    def __init__(self, monkeypatch, descriptors=(), *, create_error=0, enum_error_at=None,
                 desc_error_at=None, null_factory=False, null_adapter=False):
        self.kept = []
        self.released = []
        self.indices = []
        self.this_pointers = []
        self.iid = None
        self.load_args = None
        calltype = getattr(ct, "WINFUNCTYPE", ct.CFUNCTYPE)
        monkeypatch.setattr(ct, "WINFUNCTYPE", calltype, raising=False)
        monkeypatch.setattr(probe, "sys", SimpleNamespace(platform="win32"))

        def com_object(label, size, method_slot, callback, *args):
            def release(this):
                self.this_pointers.append((this, address))
                self.released.append(label)
                return 0
            release_fn = calltype(ct.c_uint32, ct.c_void_p)(release)
            method_fn = calltype(ct.c_int32, ct.c_void_p, *args)(callback)
            vtable = (ct.c_void_p * size)()
            vtable[2] = ct.cast(release_fn, ct.c_void_p).value
            vtable[method_slot] = ct.cast(method_fn, ct.c_void_p).value
            obj = ct.pointer(ct.cast(vtable, ct.POINTER(ct.c_void_p)))
            address = ct.cast(obj, ct.c_void_p).value
            self.kept.extend((release_fn, method_fn, vtable, obj))
            return address

        addresses = []
        for index, desc in enumerate(descriptors):
            def get_desc(this, output, index=index, desc=desc):
                self.this_pointers.append((this, addresses[index]))
                if index == desc_error_at:
                    return ct.c_int32(0x80004005).value
                ct.memmove(output, ct.byref(desc), ct.sizeof(desc))
                return 0
            addresses.append(com_object(index, 11, 10, get_desc, ct.POINTER(probe._AdapterDesc1)))

        def enumerate_adapter(this, index, output):
            self.this_pointers.append((this, factory_address))
            self.indices.append(index)
            if index == enum_error_at:
                return ct.c_int32(0x80004005).value
            if index >= len(addresses):
                return ct.c_int32(0x887A0002).value
            output[0] = None if null_adapter else addresses[index]
            return 0
        factory_address = com_object("factory", 14, 12, enumerate_adapter, ct.c_uint32, ct.POINTER(ct.c_void_p))

        def create(iid, output):
            self.iid = bytes(iid._obj)
            if create_error:
                return create_error
            output._obj.value = None if null_factory else factory_address
            return 0
        self.create = create

        def load(name, **kwargs):
            self.load_args = (name, kwargs)
            return SimpleNamespace(CreateDXGIFactory1=create)
        monkeypatch.setattr(ct, "WinDLL", load, raising=False)


def test_native_layout_and_enumeration_with_explicit_software_and_zero(monkeypatch):
    assert ct.sizeof(probe._GUID) == 16 and ct.sizeof(probe._LUID) == 8
    assert ct.sizeof(probe._HRESULT) == 4
    assert ct.sizeof(probe._AdapterDesc1) == (312 if ct.sizeof(ct.c_void_p) == 8 else 296)
    assert probe._AdapterDesc1.dedicated_video_memory.offset == 272
    native = FakeDXGI(monkeypatch, (descriptor("Hardware α 🖥"), descriptor("Basic Render", 0, 0, 2)))
    value = probe.inspect_accelerators()
    assert value.status == "available"
    assert [item.display_name for item in value.adapters] == ["Hardware α 🖥", "Basic Render"]
    assert value.adapters[0].dedicated_video_memory_bytes == 8 * 1024**3
    assert value.adapters[0].shared_system_memory_bytes == 16 * 1024**3
    assert value.adapters[1].classification == "software"
    assert value.adapters[1].dedicated_video_memory_bytes == value.adapters[1].shared_system_memory_bytes == 0
    assert native.iid.hex() == "78ae0a776ff2ba4da829253c83d1b387"
    assert native.load_args == ("dxgi.dll", {"winmode": 0x800})
    assert native.create.restype is ct.c_int32 and len(native.create.argtypes) == 2
    assert native.indices == [0, 1, 2] and native.released == [0, 1, "factory"]
    assert all(actual == expected for actual, expected in native.this_pointers)


@pytest.mark.parametrize("flags,expected", [(0, "hardware"), (2, "software"), (1, "unknown"), (3, "unknown"), (0xFFFFFFFF, "unknown")])
def test_classification_uses_only_native_flags(monkeypatch, flags, expected):
    FakeDXGI(monkeypatch, (descriptor("Software Adapter", flags=flags),))
    assert probe.inspect_accelerators().adapters[0].classification == expected


def test_unrepresentable_memory_is_unknown_without_losing_other_facts(monkeypatch):
    if ct.sizeof(ct.c_size_t) < 8:
        pytest.skip("32-bit SIZE_T cannot represent this input")
    FakeDXGI(monkeypatch, (descriptor(dedicated=2**53, shared=2**53 - 1),))
    value = probe.inspect_accelerators().adapters[0]
    assert value.dedicated_video_memory_bytes is None and value.shared_system_memory_bytes == 2**53 - 1


@pytest.mark.parametrize("options,released", [
    ({"create_error": -1}, []), ({"null_factory": True}, []),
    ({"enum_error_at": 0}, ["factory"]), ({"enum_error_at": 1}, [0, "factory"]),
    ({"desc_error_at": 1}, [0, 1, "factory"]), ({"null_adapter": True}, ["factory"]),
])
def test_native_errors_discard_partial_results_and_release_acquired_references(monkeypatch, options, released):
    native = FakeDXGI(monkeypatch, (descriptor(), descriptor()), **options)
    assert probe.inspect_accelerators() == AcceleratorProfile(status="unknown", adapters=())
    assert native.released == released


@pytest.mark.parametrize("kind", ["blank", "unterminated", "invalid_utf16"])
def test_bad_descriptors_are_unknown_and_released(monkeypatch, kind):
    desc = descriptor("  ")
    if kind == "unterminated":
        desc.description[:] = [65] * 128
    if kind == "invalid_utf16":
        desc.description[0] = 0xD800
    native = FakeDXGI(monkeypatch, (desc,))
    assert probe.inspect_accelerators().status == "unknown"
    assert native.released == [0, "factory"]


def test_empty_enumeration_is_available_but_overflow_is_unknown(monkeypatch):
    empty = FakeDXGI(monkeypatch)
    assert probe.inspect_accelerators() == AcceleratorProfile(status="available", adapters=())
    assert empty.released == ["factory"]
    bounded = FakeDXGI(monkeypatch, (descriptor(),) * 65)
    assert probe.inspect_accelerators().status == "unknown"
    assert bounded.indices == list(range(65)) and bounded.released == list(range(65)) + ["factory"]


@pytest.mark.parametrize("error", [OSError("load failed"), AttributeError("API unavailable")])
def test_missing_dxgi_is_unknown(monkeypatch, error):
    monkeypatch.setattr(probe, "sys", SimpleNamespace(platform="win32"))
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(ct, "WinDLL", fail, raising=False)
    assert probe.inspect_accelerators().status == "unknown"


@pytest.mark.parametrize("platform", ["linux", "darwin", "freebsd"])
def test_non_windows_never_loads_windows_api(monkeypatch, platform):
    monkeypatch.setattr(probe, "sys", SimpleNamespace(platform=platform))
    def fail(*args, **kwargs):
        raise AssertionError("Windows probe on another platform")
    monkeypatch.setattr(ct, "WinDLL", fail, raising=False)
    assert probe.inspect_accelerators() == AcceleratorProfile(status="unsupported", adapters=())


def test_real_host_probe_smoke():
    # Real DXGI on Windows CI; no physical GPU or nonempty result is required.
    value = probe.inspect_accelerators()
    assert value.status in (("available", "unknown") if sys.platform == "win32" else ("unsupported",))
    assert AcceleratorProfile.model_validate_json(value.model_dump_json()) == value


def test_get_has_no_settings_db_file_process_network_or_other_setup_effects(tmp_path, monkeypatch):
    database = Database(tmp_path / "accelerators.db", tmp_path, tmp_path / "missing.bin")
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
                patches.setattr(setup_api, "inspect_hardware", deny)
                patches.setattr(builtins, "open", read_only_open)
                patches.setattr(sqlite3, "connect", deny)
                patches.setattr(socket, "getaddrinfo", deny)
                patches.setattr(socket.socket, "connect", deny)
                patches.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny)
                patches.setattr(subprocess, "Popen", deny)
                patches.setattr(os, "system", deny)
                for name in ("create_subprocess_exec", "create_subprocess_shell"):
                    patches.setattr(asyncio, name, deny)
                for name in ("mkdir", "write_text", "write_bytes", "touch", "unlink", "rename"):
                    patches.setattr(Path, name, deny)
                for _ in range(2):
                    response = await client.get("/v1/setup/accelerators")
                    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
                    AcceleratorProfile.model_validate_json(response.content)
                patches.setattr(setup_api, "inspect_accelerators", deny)
                for method in ("POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                    assert (await client.request(method, "/v1/setup/accelerators")).status_code == 405
                assert (await client.get("/v1/setup/models")).json() == setup_api.BUNDLED_MODEL_CATALOG.model_dump(mode="json")
    asyncio.run(exercise())
    assert not attempts and asyncio.run(database.get_settings()) == settings
    with sqlite3.connect(database.db_path) as connection:
        assert list(connection.iterdump()) == before
