"""Exercise Win32 resource handling with test-owned memory, never host clipboard."""

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
from jarvis_agent.domain.tool_inputs import ClipboardReadInput, UrlOpenInput
from jarvis_agent.domain.tool_outputs import ClipboardReadOutput, NoDataOutput
from jarvis_agent.provider_registry import CapabilityProviderRegistry, CapabilityUnavailableError
from jarvis_agent.providers.windows import clipboard_read
from jarvis_agent.providers.windows.clipboard_read import WindowsClipboardReadProvider
from jarvis_agent.providers.windows.url_open import WindowsUrlOpenProvider
from jarvis_agent.tool_runtime import ToolProvider, ToolRuntime


@pytest.fixture(autouse=True)
def native(monkeypatch):
    clipboard_read._native_api.cache_clear()
    # Windows keeps real ctypes LastError/WinError semantics; Linux supplies fakes.
    if sys.platform != "win32":
        error_state = threading.local()
        monkeypatch.setattr(ctypes, "set_last_error", lambda code: setattr(error_state, "code", code), raising=False)
        monkeypatch.setattr(ctypes, "get_last_error", lambda: getattr(error_state, "code", 0), raising=False)

        def win_error(code, message):
            error = OSError(code, message)
            error.winerror = code
            return error

        monkeypatch.setattr(ctypes, "WinError", win_error, raising=False)

    state = SimpleNamespace(events=[], threads=[], errors={}, handle=0x12345678ABCDEF)
    state.results = dict(OpenClipboard=1, IsClipboardFormatAvailable=1,
                         GetClipboardData=state.handle, GlobalUnlock=0, CloseClipboard=1)

    def set_data(data):
        state.buffer = ctypes.create_string_buffer(data)
        state.results.update(GlobalLock=ctypes.addressof(state.buffer), GlobalSize=len(data))

    state.set_data = set_data
    set_data("fixture".encode("utf-16-le") + b"\x00\x00")

    def function(name):
        def invoke(*args):
            state.events.append(name)
            state.threads.append(threading.get_ident())
            if name in state.errors:
                ctypes.set_last_error(state.errors[name])
            return state.results[name]
        return Mock(side_effect=invoke)

    state.user32 = SimpleNamespace(**{name: function(name) for name in (
        "OpenClipboard", "IsClipboardFormatAvailable", "GetClipboardData", "CloseClipboard")})
    state.kernel32 = SimpleNamespace(**{name: function(name) for name in (
        "GlobalLock", "GlobalSize", "GlobalUnlock")})
    libraries = {"user32.dll": state.user32, "kernel32.dll": state.kernel32}
    state.loader = Mock(side_effect=lambda name, **kwargs: libraries[name])
    # Always intercept DLL loading, including tests using the actual Windows host.
    monkeypatch.setattr(ctypes, "WinDLL", state.loader, raising=False)
    forbidden = Mock(side_effect=AssertionError("Shell/subprocess is forbidden"))
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(os, "popen", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    yield state
    clipboard_read._native_api.cache_clear()


@pytest.fixture
def windows_host(monkeypatch, native):
    monkeypatch.setattr(clipboard_read, "sys", SimpleNamespace(platform="win32"))
    return native


def runtime():
    registry = CapabilityProviderRegistry()
    provider: ToolProvider = WindowsClipboardReadProvider()
    registry.register("clipboard.read", provider)
    return ToolRuntime(registry)


@pytest.mark.parametrize("text", ["", "   ", "\t\r\n\n", "Grüße 世界", "😀🧑🏽‍💻", "first\r\n second\n\tlast ", "e\u0301\u00e9\ufeff", "x" * 20000])
def test_semantic_execution_preserves_exact_text(windows_host, text):
    windows_host.set_data(text.encode("utf-16-le") + b"\x00\x00" + b"padding")
    result = asyncio.run(runtime().execute("clipboard.read", {}))
    assert type(result) is ClipboardReadOutput and result.model_dump() == {"text": text}
    assert windows_host.events == ["OpenClipboard", "IsClipboardFormatAvailable", "GetClipboardData",
                                   "GlobalLock", "GlobalSize", "GlobalUnlock", "CloseClipboard"]
    windows_host.user32.OpenClipboard.assert_called_once_with(None)
    windows_host.user32.IsClipboardFormatAvailable.assert_called_once_with(13)
    windows_host.user32.GetClipboardData.assert_called_once_with(13)
    windows_host.kernel32.GlobalLock.assert_called_once_with(windows_host.handle)
    windows_host.kernel32.GlobalSize.assert_called_once_with(windows_host.handle)
    windows_host.kernel32.GlobalUnlock.assert_called_once_with(windows_host.handle)
    windows_host.user32.CloseClipboard.assert_called_once_with()


def test_no_unicode_format_means_empty_text_without_retrieval_or_lock(windows_host):
    windows_host.results["IsClipboardFormatAvailable"] = 0
    # A stale prior LastError must not turn normal absence into an error.
    windows_host.errors["OpenClipboard"] = 5
    assert asyncio.run(runtime().execute("clipboard.read", {})).text == ""
    assert windows_host.events == ["OpenClipboard", "IsClipboardFormatAvailable", "CloseClipboard"]


@pytest.mark.parametrize("operation, expected", [
    ("OpenClipboard", ["OpenClipboard"]),
    ("IsClipboardFormatAvailable", ["OpenClipboard", "IsClipboardFormatAvailable", "CloseClipboard"]),
    ("GetClipboardData", ["OpenClipboard", "IsClipboardFormatAvailable", "GetClipboardData", "CloseClipboard"]),
    ("GlobalLock", ["OpenClipboard", "IsClipboardFormatAvailable", "GetClipboardData", "GlobalLock", "CloseClipboard"]),
    ("GlobalSize", ["OpenClipboard", "IsClipboardFormatAvailable", "GetClipboardData", "GlobalLock", "GlobalSize", "GlobalUnlock", "CloseClipboard"]),
    ("GlobalUnlock", ["OpenClipboard", "IsClipboardFormatAvailable", "GetClipboardData", "GlobalLock", "GlobalSize", "GlobalUnlock", "CloseClipboard"]),
    ("CloseClipboard", ["OpenClipboard", "IsClipboardFormatAvailable", "GetClipboardData", "GlobalLock", "GlobalSize", "GlobalUnlock", "CloseClipboard"]),
])
def test_native_failure_is_explicit_and_releases_acquired_resources(windows_host, operation, expected):
    windows_host.results[operation] = 0
    windows_host.errors[operation] = 5
    with pytest.raises(OSError, match=operation) as error:
        asyncio.run(runtime().execute("clipboard.read", {}))
    assert error.value.winerror == 5
    assert windows_host.events == expected


@pytest.mark.parametrize("operation", ["OpenClipboard", "GetClipboardData", "GlobalLock", "GlobalSize", "CloseClipboard"])
def test_required_api_failure_without_last_error_is_still_an_error(windows_host, operation):
    windows_host.results[operation] = 0
    with pytest.raises(OSError, match=operation):
        asyncio.run(runtime().execute("clipboard.read", {}))


@pytest.mark.parametrize("unlock_result", [0, 1])
def test_unlock_success_handles_zero_and_remaining_locks(windows_host, unlock_result):
    windows_host.results["GlobalUnlock"] = unlock_result
    windows_host.errors["GlobalSize"] = 5  # cleared before ambiguous zero result
    assert asyncio.run(runtime().execute("clipboard.read", {})).text == "fixture"
    windows_host.kernel32.GlobalUnlock.assert_called_once_with(windows_host.handle)


def test_copy_error_preserves_exception_and_unlocks_then_closes(monkeypatch, windows_host):
    failure = OSError("controlled copy failure")
    copy = Mock(side_effect=failure)
    monkeypatch.setattr(ctypes, "string_at", copy)
    with pytest.raises(OSError) as error:
        asyncio.run(runtime().execute("clipboard.read", {}))
    assert error.value is failure
    copy.assert_called_once_with(windows_host.results["GlobalLock"], windows_host.results["GlobalSize"])
    assert windows_host.events[-2:] == ["GlobalUnlock", "CloseClipboard"]


def test_cleanup_failures_still_close_and_retain_exception_context(windows_host):
    windows_host.results.update(GlobalSize=0, GlobalUnlock=0, CloseClipboard=0)
    windows_host.errors.update(GlobalSize=6, GlobalUnlock=7, CloseClipboard=8)
    with pytest.raises(OSError, match="CloseClipboard") as error:
        asyncio.run(runtime().execute("clipboard.read", {}))
    assert error.value.winerror == 8
    assert error.value.__context__.winerror == 7
    assert error.value.__context__.__context__.winerror == 6
    assert windows_host.events[-2:] == ["GlobalUnlock", "CloseClipboard"]


@pytest.mark.parametrize("data, error_type", [
    (b"x", ValueError), (b"A\x00", ValueError), (b"\x00\xd8\x00\x00", UnicodeDecodeError),
])
def test_malformed_unicode_is_an_error_after_resources_are_closed(windows_host, data, error_type):
    windows_host.set_data(data)
    with pytest.raises(error_type):
        asyncio.run(runtime().execute("clipboard.read", {}))
    assert windows_host.events[-2:] == ["GlobalUnlock", "CloseClipboard"]


def test_terminator_is_aligned_and_scan_cannot_escape_allocation(windows_host):
    # An unaligned zero pair between A and U+0100 must not truncate the text.
    windows_host.set_data(b"A\x00\x00\x01\x00\x00")
    assert asyncio.run(runtime().execute("clipboard.read", {})).text == "A\u0100"
    # A terminator exists in the test buffer, but OUTSIDE the reported allocation.
    windows_host.results["GlobalSize"] = 4
    with pytest.raises(ValueError, match="not NUL-terminated"):
        asyncio.run(runtime().execute("clipboard.read", {}))


def test_native_bindings_use_system_dlls_and_pointer_sized_types(windows_host):
    asyncio.run(runtime().execute("clipboard.read", {}))
    assert windows_host.loader.call_args_list == [
        call("user32.dll", use_last_error=True, winmode=0x800),
        call("kernel32.dll", use_last_error=True, winmode=0x800),
    ]
    for function, args, result in (
        (windows_host.user32.OpenClipboard, [wintypes.HWND], wintypes.BOOL),
        (windows_host.user32.IsClipboardFormatAvailable, [wintypes.UINT], wintypes.BOOL),
        (windows_host.user32.GetClipboardData, [wintypes.UINT], wintypes.HANDLE),
        (windows_host.user32.CloseClipboard, [], wintypes.BOOL),
        (windows_host.kernel32.GlobalLock, [wintypes.HGLOBAL], ctypes.c_void_p),
        (windows_host.kernel32.GlobalSize, [wintypes.HGLOBAL], ctypes.c_size_t),
        (windows_host.kernel32.GlobalUnlock, [wintypes.HGLOBAL], wintypes.BOOL),
    ):
        assert function.argtypes == args and function.restype is result
    assert ctypes.sizeof(wintypes.HANDLE) == ctypes.sizeof(ctypes.c_void_p)


def test_native_bindings_are_reused_without_caching_clipboard_text(windows_host):
    assert asyncio.run(runtime().execute("clipboard.read", {})).text == "fixture"
    windows_host.set_data("changed".encode("utf-16-le") + b"\x00\x00")
    assert asyncio.run(runtime().execute("clipboard.read", {})).text == "changed"
    assert windows_host.loader.call_count == 2  # two DLLs, not two per read
    assert windows_host.user32.OpenClipboard.call_count == 2
    assert windows_host.user32.CloseClipboard.call_count == 2


def test_dll_loading_error_propagates_without_clipboard_access(windows_host):
    failure = OSError("controlled DLL load failure")
    windows_host.loader.side_effect = failure
    with pytest.raises(OSError) as error:
        asyncio.run(runtime().execute("clipboard.read", {}))
    assert error.value is failure
    assert windows_host.events == []


@pytest.mark.parametrize("capability", [key for key in CAPABILITY_CATALOG if key != "clipboard.read"] + list(LEGACY_TOOL_TO_CAPABILITY) + ["Clipboard.Read", "clipboard.read ", "unknown.foo"])
def test_exact_capability_identity_before_native_loading(windows_host, capability):
    with pytest.raises(KeyError) as error:
        asyncio.run(WindowsClipboardReadProvider().execute(capability, ClipboardReadInput()))
    assert error.value.args == (capability,)
    windows_host.loader.assert_not_called()


@pytest.mark.parametrize("input_data", [None, {"extra": True}, NoDataOutput(), UrlOpenInput(url="https://example.test"), ClipboardReadInput().model_copy(update={"extra": True})])
@pytest.mark.parametrize("direct", [False, True])
def test_invalid_or_forged_input_never_loads_native_boundary(windows_host, input_data, direct):
    target = WindowsClipboardReadProvider() if direct else runtime()
    with pytest.raises(ValidationError):
        asyncio.run(target.execute("clipboard.read", input_data))
    windows_host.loader.assert_not_called()


def test_c1_rejects_invalid_input_before_provider(monkeypatch, windows_host):
    provider = WindowsClipboardReadProvider()
    execute = AsyncMock(wraps=provider.execute)
    monkeypatch.setattr(provider, "execute", execute)
    with pytest.raises(ValidationError):
        asyncio.run(ToolRuntime(provider).execute("clipboard.read", {"extra": True}))
    execute.assert_not_called()
    windows_host.loader.assert_not_called()


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_non_windows_fails_closed_before_native_loading(monkeypatch, native, platform):
    monkeypatch.setattr(clipboard_read, "sys", SimpleNamespace(platform=platform))
    with pytest.raises(OSError, match="requires a Windows host"):
        asyncio.run(runtime().execute("clipboard.read", {}))
    native.loader.assert_not_called()


def test_actual_platform_with_only_win32_boundary_mocked(native):
    assert clipboard_read.sys is sys
    if sys.platform == "win32":
        assert asyncio.run(runtime().execute("clipboard.read", {})).text == "fixture"
        native.user32.OpenClipboard.assert_called_once_with(None)
    else:
        with pytest.raises(OSError, match="requires a Windows host"):
            asyncio.run(runtime().execute("clipboard.read", {}))
        native.loader.assert_not_called()


def test_all_native_operations_stay_on_one_worker_thread_with_responsive_loop(windows_host):
    async def check():
        loop = asyncio.get_running_loop()
        loop_thread = threading.get_ident()
        entered, release = asyncio.Event(), threading.Event()
        invoke = windows_host.user32.OpenClipboard.side_effect

        def open_clipboard(*args):
            result = invoke(*args)
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(5), "Loop did not release worker"
            return result

        windows_host.user32.OpenClipboard.side_effect = open_clipboard
        task = asyncio.create_task(runtime().execute("clipboard.read", {}))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            assert not task.done()
            assert windows_host.threads[0] != loop_thread
        finally:
            release.set()
            await task
        assert len(windows_host.threads) == 7 and len(set(windows_host.threads)) == 1

    asyncio.run(check())


def test_registration_is_explicit_and_only_selected_capabilities_are_available(native):
    registry = CapabilityProviderRegistry()
    provider = WindowsClipboardReadProvider()
    assert registry.available_capabilities() == ()
    with pytest.raises(CapabilityUnavailableError):
        registry.resolve("clipboard.read")
    registry.register("clipboard.read", provider)
    assert registry.available_capabilities() == ("clipboard.read",)
    assert registry.resolve("clipboard.read") is provider
    for capability in CAPABILITY_CATALOG.keys() - {"clipboard.read"}:
        with pytest.raises(CapabilityUnavailableError):
            registry.resolve(capability)
    registry.register("url.open", WindowsUrlOpenProvider())
    assert registry.available_capabilities() == ("clipboard.read", "url.open")
    for capability in CAPABILITY_CATALOG.keys() - {"clipboard.read", "url.open"}:
        with pytest.raises(CapabilityUnavailableError):
            registry.resolve(capability)
    assert CapabilityProviderRegistry().available_capabilities() == ()
    native.loader.assert_not_called()
