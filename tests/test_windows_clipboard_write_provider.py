"""Native write/ownership tests use only fake HWNDs and test-owned byte buffers."""

import asyncio
import ctypes
import os
import subprocess
import sys
import threading
from ctypes import wintypes
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from pydantic import ValidationError

from jarvis_agent.domain.capability_catalog import CAPABILITY_CATALOG, LEGACY_TOOL_TO_CAPABILITY
from jarvis_agent.domain.tool_inputs import ClipboardWriteInput
from jarvis_agent.domain.tool_outputs import NoDataOutput
from jarvis_agent.provider_registry import CapabilityProviderRegistry, CapabilityUnavailableError
from jarvis_agent.providers.windows import clipboard_write
from jarvis_agent.providers.windows.clipboard_read import WindowsClipboardReadProvider
from jarvis_agent.providers.windows.clipboard_write import WindowsClipboardWriteProvider
from jarvis_agent.providers.windows.url_open import WindowsUrlOpenProvider
from jarvis_agent.tool_runtime import ToolProvider, ToolRuntime


SUCCESS = "CreateWindowExW OpenClipboard EmptyClipboard GlobalAlloc GlobalLock memmove GlobalUnlock SetClipboardData CloseClipboard DestroyWindow".split()


@pytest.fixture(autouse=True)
def native(monkeypatch):
    clipboard_write._native_api.cache_clear()
    if sys.platform != "win32":
        error_state = threading.local()
        monkeypatch.setattr(ctypes, "set_last_error", lambda code: setattr(error_state, "code", code), raising=False)
        monkeypatch.setattr(ctypes, "get_last_error", lambda: getattr(error_state, "code", 0), raising=False)

        def win_error(code, message):
            error = OSError(code, message)
            error.winerror = code
            return error

        monkeypatch.setattr(ctypes, "WinError", win_error, raising=False)

    state = SimpleNamespace(events=[], threads=[], failures={}, errors={}, exceptions={},
                            owner=0x123456781234, handle=0x234567892345, transferred=False,
                            window_live=False, opened=False, allocated=False, locked=False,
                            clipboard=b"previous content", copied=None)
    real_memmove = ctypes.memmove

    def invoke(name, *args):
        state.events.append(name)
        state.threads.append(threading.get_ident())
        if name in state.exceptions:
            raise state.exceptions[name]
        if name in state.errors:
            ctypes.set_last_error(state.errors[name])
        if name in state.failures:
            return state.failures[name]
        if name == "CreateWindowExW":
            state.window_live = True
            return state.owner
        if name == "OpenClipboard":
            assert state.window_live and args == (state.owner,)
            state.opened = True
        elif name == "EmptyClipboard":
            assert state.opened
            state.clipboard = None
        elif name == "GlobalAlloc":
            assert args[0] == 0x0002 and args[1] >= 2
            state.buffer = ctypes.create_string_buffer(args[1])
            state.allocated = True
            state.transferred = False
            return state.handle
        elif name == "GlobalLock":
            assert state.allocated and args == (state.handle,)
            state.locked = True
            return ctypes.addressof(state.buffer)
        elif name == "memmove":
            assert state.locked and args[0] == ctypes.addressof(state.buffer)
            assert args[2] == ctypes.sizeof(state.buffer) == len(args[1])
            real_memmove(*args)
            state.copied = state.buffer.raw
        elif name == "GlobalUnlock":
            assert state.locked and args == (state.handle,)
            state.locked = False
            return 0
        elif name == "SetClipboardData":
            assert state.opened and not state.locked and args == (13, state.handle)
            state.transferred = True
            state.clipboard = state.buffer.raw
            return state.handle
        elif name == "GlobalFree":
            assert state.allocated and not state.transferred and args == (state.handle,)
            state.allocated = False
            state.locked = False  # GlobalFree can release a still-locked allocation.
            return None
        elif name == "CloseClipboard":
            assert state.opened
            state.opened = False
        elif name == "DestroyWindow":
            assert state.window_live and args == (state.owner,)
            state.window_live = False
        return 1

    state.user32 = SimpleNamespace(**{name: Mock(side_effect=lambda *args, n=name: invoke(n, *args)) for name in (
        "CreateWindowExW", "DestroyWindow", "OpenClipboard", "EmptyClipboard", "SetClipboardData", "CloseClipboard")})
    state.kernel32 = SimpleNamespace(**{name: Mock(side_effect=lambda *args, n=name: invoke(n, *args)) for name in (
        "GlobalAlloc", "GlobalLock", "GlobalUnlock", "GlobalFree")})
    libraries = {"user32.dll": state.user32, "kernel32.dll": state.kernel32}
    state.loader = Mock(side_effect=lambda name, **kwargs: libraries[name])
    monkeypatch.setattr(ctypes, "WinDLL", state.loader, raising=False)
    monkeypatch.setattr(ctypes, "memmove", Mock(side_effect=lambda *args: invoke("memmove", *args)))
    forbidden = Mock(side_effect=AssertionError("Shell/subprocess is forbidden"))
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(os, "popen", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    yield state
    clipboard_write._native_api.cache_clear()


@pytest.fixture
def windows_host(monkeypatch, native):
    monkeypatch.setattr(clipboard_write, "sys", SimpleNamespace(platform="win32"))
    return native


def runtime():
    registry = CapabilityProviderRegistry()
    provider: ToolProvider = WindowsClipboardWriteProvider()
    registry.register("clipboard.write", provider)
    return ToolRuntime(registry)


@pytest.mark.parametrize("text", ["", "   ", "\t", "\r\n\n", "Grüße 世界", "😀🧑🏽‍💻", "e\u0301é", "\ufeffBOM", "first\r\n second\n\tlast ", "x" * 20000, "before\x00after"])
def test_semantic_write_transfers_exact_utf16_bytes_without_free(windows_host, text):
    result = asyncio.run(runtime().execute("clipboard.write", {"text": text}))
    assert type(result) is NoDataOutput and result.model_dump() == {}
    assert windows_host.events == SUCCESS
    assert windows_host.copied == windows_host.clipboard == text.encode("utf-16-le") + b"\x00\x00"
    windows_host.user32.CreateWindowExW.assert_called_once_with(0, "STATIC", None, 0, 0, 0, 0, 0, -3, None, None, None)
    windows_host.user32.OpenClipboard.assert_called_once_with(windows_host.owner)
    windows_host.user32.SetClipboardData.assert_called_once_with(13, windows_host.handle)
    windows_host.kernel32.GlobalFree.assert_not_called()
    assert windows_host.transferred and not windows_host.locked
    assert not windows_host.opened and not windows_host.window_live


@pytest.mark.parametrize("operation, sequence", [
    ("CreateWindowExW", "CreateWindowExW"),
    ("OpenClipboard", "CreateWindowExW OpenClipboard DestroyWindow"),
    ("EmptyClipboard", "CreateWindowExW OpenClipboard EmptyClipboard CloseClipboard DestroyWindow"),
    ("GlobalAlloc", "CreateWindowExW OpenClipboard EmptyClipboard GlobalAlloc CloseClipboard DestroyWindow"),
    ("GlobalLock", "CreateWindowExW OpenClipboard EmptyClipboard GlobalAlloc GlobalLock GlobalFree CloseClipboard DestroyWindow"),
    ("memmove", "CreateWindowExW OpenClipboard EmptyClipboard GlobalAlloc GlobalLock memmove GlobalUnlock GlobalFree CloseClipboard DestroyWindow"),
    ("GlobalUnlock", "CreateWindowExW OpenClipboard EmptyClipboard GlobalAlloc GlobalLock memmove GlobalUnlock GlobalFree CloseClipboard DestroyWindow"),
    ("SetClipboardData", "CreateWindowExW OpenClipboard EmptyClipboard GlobalAlloc GlobalLock memmove GlobalUnlock SetClipboardData GlobalFree CloseClipboard DestroyWindow"),
    ("CloseClipboard", " ".join(SUCCESS)),
    ("DestroyWindow", " ".join(SUCCESS)),
])
def test_failure_cleanup_matches_acquired_resources(windows_host, operation, sequence):
    failure = OSError("controlled memory copy error")
    if operation == "memmove":
        windows_host.exceptions[operation] = failure
    else:
        windows_host.failures[operation] = 0
        windows_host.errors[operation] = 5
    with pytest.raises(OSError) as error:
        asyncio.run(runtime().execute("clipboard.write", {"text": "changed"}))
    if operation == "memmove":
        assert error.value is failure
    else:
        assert error.value.winerror == 5 and operation in str(error.value)
    assert error.value.__context__ is None
    assert windows_host.events == sequence.split()
    if operation in {"CloseClipboard", "DestroyWindow"}:
        assert windows_host.transferred
        assert windows_host.clipboard == "changed".encode("utf-16-le") + b"\x00\x00"
        windows_host.kernel32.GlobalFree.assert_not_called()
    elif operation in {"CreateWindowExW", "OpenClipboard", "EmptyClipboard"}:
        assert windows_host.clipboard == b"previous content"
        assert not windows_host.allocated
    else:
        # EmptyClipboard succeeded: no restore/snapshot or fake rollback.
        assert windows_host.clipboard is None
        assert not windows_host.transferred and not windows_host.allocated


@pytest.mark.parametrize("operation", ["CreateWindowExW", "OpenClipboard", "EmptyClipboard", "GlobalAlloc", "GlobalLock", "SetClipboardData", "CloseClipboard", "DestroyWindow"])
def test_required_zero_result_without_last_error_still_fails(windows_host, operation):
    windows_host.failures[operation] = 0
    with pytest.raises(OSError, match=operation):
        asyncio.run(runtime().execute("clipboard.write", {"text": "text"}))


def test_final_unlock_zero_is_success_and_stale_last_error_is_cleared(windows_host):
    windows_host.errors["GlobalLock"] = 5
    asyncio.run(runtime().execute("clipboard.write", {"text": "text"}))
    assert windows_host.events == SUCCESS and windows_host.transferred


def test_unexpected_remaining_lock_fails_before_transfer_and_frees(windows_host):
    windows_host.failures["GlobalUnlock"] = 1
    with pytest.raises(OSError, match="left the new allocation locked"):
        asyncio.run(runtime().execute("clipboard.write", {"text": "text"}))
    windows_host.user32.SetClipboardData.assert_not_called()
    windows_host.kernel32.GlobalFree.assert_called_once_with(windows_host.handle)
    assert not windows_host.allocated and not windows_host.locked


@pytest.mark.parametrize("free_error", [0, 6])
def test_global_free_nonnull_is_failure_and_preserves_set_error(windows_host, free_error):
    windows_host.failures.update(SetClipboardData=0, GlobalFree=windows_host.handle)
    windows_host.errors.update(SetClipboardData=5, GlobalFree=free_error)
    with pytest.raises(OSError, match="GlobalFree") as error:
        asyncio.run(runtime().execute("clipboard.write", {"text": "text"}))
    assert error.value.winerror == free_error
    assert error.value.__context__.winerror == 5
    assert windows_host.events[-3:] == ["GlobalFree", "CloseClipboard", "DestroyWindow"]


def test_all_cleanup_errors_remain_in_context_and_no_transfer_occurs(windows_host):
    copy_error = OSError("controlled copy failure")
    windows_host.exceptions["memmove"] = copy_error
    windows_host.failures.update(GlobalUnlock=0, GlobalFree=windows_host.handle, CloseClipboard=0, DestroyWindow=0)
    windows_host.errors.update(GlobalUnlock=5, GlobalFree=6, CloseClipboard=7, DestroyWindow=8)
    with pytest.raises(OSError, match="DestroyWindow") as caught:
        asyncio.run(runtime().execute("clipboard.write", {"text": "text"}))
    error = caught.value
    for code in (8, 7, 6, 5):
        assert error.winerror == code
        error = error.__context__
    assert error is copy_error
    assert windows_host.events[-4:] == ["GlobalUnlock", "GlobalFree", "CloseClipboard", "DestroyWindow"]
    windows_host.user32.SetClipboardData.assert_not_called()


def test_cleanup_errors_after_transfer_never_free_or_restore(windows_host):
    windows_host.failures.update(CloseClipboard=0, DestroyWindow=0)
    windows_host.errors.update(CloseClipboard=5, DestroyWindow=6)
    with pytest.raises(OSError, match="DestroyWindow") as error:
        asyncio.run(runtime().execute("clipboard.write", {"text": "new"}))
    assert error.value.winerror == 6 and error.value.__context__.winerror == 5
    assert windows_host.events == SUCCESS and windows_host.transferred
    assert windows_host.clipboard == b"n\x00e\x00w\x00\x00\x00"
    windows_host.kernel32.GlobalFree.assert_not_called()


def test_strict_encoding_failure_precedes_dll_loading(windows_host):
    # Domain StrictStr is unchanged; UTF-16 encoding itself rejects lone surrogates.
    with pytest.raises(UnicodeEncodeError):
        asyncio.run(runtime().execute("clipboard.write", {"text": "\ud800"}))
    windows_host.loader.assert_not_called()
    assert windows_host.events == []


@pytest.mark.parametrize("input_data", [{}, None, {"text": None}, {"text": 12}, {"text": True}, {"text": b"bytes"}, {"text": "ok", "extra": True}, NoDataOutput(), ClipboardWriteInput.model_construct(text=123), ClipboardWriteInput(text="ok").model_copy(update={"text": None})])
@pytest.mark.parametrize("direct", [False, True])
def test_invalid_and_forged_input_precedes_any_native_boundary(windows_host, input_data, direct):
    target = WindowsClipboardWriteProvider() if direct else runtime()
    with pytest.raises(ValidationError):
        asyncio.run(target.execute("clipboard.write", input_data))
    windows_host.loader.assert_not_called()
    assert windows_host.events == []


def test_c1_input_failure_precedes_provider_invocation(monkeypatch, windows_host):
    provider = WindowsClipboardWriteProvider()
    execute = AsyncMock(wraps=provider.execute)
    monkeypatch.setattr(provider, "execute", execute)
    with pytest.raises(ValidationError):
        asyncio.run(ToolRuntime(provider).execute("clipboard.write", {"text": 123}))
    execute.assert_not_called()
    windows_host.loader.assert_not_called()


@pytest.mark.parametrize("capability", [key for key in CAPABILITY_CATALOG if key != "clipboard.write"] + list(LEGACY_TOOL_TO_CAPABILITY) + ["Clipboard.Write", "clipboard.write ", "unknown.foo"])
def test_only_exact_capability_is_accepted(windows_host, capability):
    with pytest.raises(KeyError) as error:
        asyncio.run(WindowsClipboardWriteProvider().execute(capability, ClipboardWriteInput(text="text")))
    assert error.value.args == (capability,)
    windows_host.loader.assert_not_called()
    assert windows_host.events == []


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_non_windows_fails_before_loading_or_mutation(monkeypatch, native, platform):
    monkeypatch.setattr(clipboard_write, "sys", SimpleNamespace(platform=platform))
    with pytest.raises(OSError, match="requires a Windows host"):
        asyncio.run(runtime().execute("clipboard.write", {"text": "text"}))
    native.loader.assert_not_called()
    assert native.events == []


def test_actual_platform_with_native_clipboard_fully_mocked(native):
    assert clipboard_write.sys is sys
    if sys.platform == "win32":
        assert type(asyncio.run(runtime().execute("clipboard.write", {"text": "fixture"}))) is NoDataOutput
        assert native.events == SUCCESS
    else:
        with pytest.raises(OSError, match="requires a Windows host"):
            asyncio.run(runtime().execute("clipboard.write", {"text": "fixture"}))
        native.loader.assert_not_called()


def test_complete_transaction_uses_one_worker_and_keeps_loop_responsive(windows_host):
    async def check():
        loop = asyncio.get_running_loop()
        loop_thread = threading.get_ident()
        entered, release = asyncio.Event(), threading.Event()
        create = windows_host.user32.CreateWindowExW.side_effect

        def create_owner(*args):
            owner = create(*args)
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(5), "Loop did not release worker"
            return owner

        windows_host.user32.CreateWindowExW.side_effect = create_owner
        task = asyncio.create_task(runtime().execute("clipboard.write", {"text": "text"}))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            assert not task.done() and windows_host.threads[0] != loop_thread
        finally:
            release.set()
            await task
        assert windows_host.events == SUCCESS and len(set(windows_host.threads)) == 1

    asyncio.run(check())


def test_only_explicit_registration_grants_availability(native):
    registry = CapabilityProviderRegistry()
    provider = WindowsClipboardWriteProvider()
    assert registry.available_capabilities() == ()
    with pytest.raises(CapabilityUnavailableError):
        registry.resolve("clipboard.write")
    registry.register("clipboard.write", provider)
    assert registry.available_capabilities() == ("clipboard.write",)
    assert registry.resolve("clipboard.write") is provider
    for capability in CAPABILITY_CATALOG.keys() - {"clipboard.write"}:
        with pytest.raises(CapabilityUnavailableError):
            registry.resolve(capability)
    registry.register("url.open", WindowsUrlOpenProvider())
    registry.register("clipboard.read", WindowsClipboardReadProvider())
    assert registry.available_capabilities() == ("clipboard.read", "clipboard.write", "url.open")
    for capability in CAPABILITY_CATALOG.keys() - {"clipboard.read", "clipboard.write", "url.open"}:
        with pytest.raises(CapabilityUnavailableError):
            registry.resolve(capability)
    assert CapabilityProviderRegistry().available_capabilities() == ()
    native.loader.assert_not_called()


def test_bindings_are_lazy_reused_and_pointer_sized(windows_host):
    assert windows_host.loader.call_count == 0
    asyncio.run(runtime().execute("clipboard.write", {"text": "one"}))
    asyncio.run(runtime().execute("clipboard.write", {"text": "two"}))
    assert windows_host.loader.call_args_list == [call("user32.dll", use_last_error=True, winmode=0x800), call("kernel32.dll", use_last_error=True, winmode=0x800)]
    assert windows_host.clipboard == "two".encode("utf-16-le") + b"\x00\x00"
    assert windows_host.user32.CreateWindowExW.call_count == windows_host.user32.DestroyWindow.call_count == 2
    for function, arguments, result in (
        (windows_host.user32.CreateWindowExW, [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                             ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                             wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p], wintypes.HWND),
        (windows_host.user32.DestroyWindow, [wintypes.HWND], wintypes.BOOL),
        (windows_host.user32.OpenClipboard, [wintypes.HWND], wintypes.BOOL),
        (windows_host.user32.EmptyClipboard, [], wintypes.BOOL),
        (windows_host.user32.SetClipboardData, [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE),
        (windows_host.user32.CloseClipboard, [], wintypes.BOOL),
        (windows_host.kernel32.GlobalAlloc, [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL),
        (windows_host.kernel32.GlobalLock, [wintypes.HGLOBAL], ctypes.c_void_p),
        (windows_host.kernel32.GlobalUnlock, [wintypes.HGLOBAL], wintypes.BOOL),
        (windows_host.kernel32.GlobalFree, [wintypes.HGLOBAL], wintypes.HGLOBAL),
    ):
        assert function.argtypes == arguments and function.restype is result


def test_dll_load_failure_propagates_before_any_resources(windows_host):
    failure = OSError("controlled loader error")
    windows_host.loader.side_effect = failure
    with pytest.raises(OSError) as error:
        asyncio.run(runtime().execute("clipboard.write", {"text": "text"}))
    assert error.value is failure and windows_host.events == []
