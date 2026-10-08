"""Real provider composition; every native opener is mocked, never a browser."""

import asyncio
import os
import sys
import threading
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from jarvis_agent.domain.capability_catalog import CAPABILITY_CATALOG
from jarvis_agent.domain.tool_inputs import UrlOpenInput
from jarvis_agent.domain.tool_outputs import NoDataOutput
from jarvis_agent.provider_registry import CapabilityProviderRegistry, CapabilityUnavailableError
from jarvis_agent.providers.windows import url_open
from jarvis_agent.providers.windows.url_open import WindowsUrlOpenProvider
from jarvis_agent.tool_runtime import ToolProvider, ToolRuntime


@pytest.fixture
def native_opener(monkeypatch):
    opener = Mock(return_value=None)
    # Patch the actual native attribute on Windows; supply it for Linux fakes.
    monkeypatch.setattr(os, "startfile", opener, raising=False)
    forbidden = Mock(side_effect=AssertionError("Shell/subprocess execution is forbidden"))
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(os, "popen", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    return opener


@pytest.fixture
def windows_host(monkeypatch, native_opener):
    # Do not change process-global sys.platform (asyncio also consults it).
    monkeypatch.setattr(url_open, "sys", SimpleNamespace(platform="win32"))
    return native_opener


def runtime_with_provider():
    registry = CapabilityProviderRegistry()
    provider: ToolProvider = WindowsUrlOpenProvider()
    registry.register("url.open", provider)
    return ToolRuntime(registry)


@pytest.mark.parametrize("raw_url, expected", [
    ("https://example.test", "https://example.test/"),
    ("http://example.test/a?q=one&next=two#part", "http://example.test/a?q=one&next=two#part"),
    ('https://example.test/a?q=%25PATH%25&x=$(ignored);%22quoted%22',
     'https://example.test/a?q=%25PATH%25&x=$(ignored);%22quoted%22'),
    ("https://EXAMPLE.test:443/a%20b", "https://example.test/a%20b"),
])
def test_validated_url_is_passed_once_as_one_native_argument(windows_host, raw_url, expected):
    result = asyncio.run(runtime_with_provider().execute("url.open", {"url": raw_url}))
    assert type(result) is NoDataOutput and result.model_dump() == {}
    windows_host.assert_called_once_with(expected, "open")


@pytest.mark.parametrize("raw_input", [
    {}, {"url": ""}, {"url": "file:///C:/Windows/test.exe"},
    {"url": "javascript:alert(1)"}, {"url": "ftp://example.test"},
    {"url": "mailto:person@example.test"}, {"url": "ms-settings:"},
    {"url": "C:\\Windows\\test.exe"}, {"url": 123},
    {"url": "https://example.test/a b"}, {"url": 'https://example.test/?q="quoted"'},
    {"url": "https://example.test", "extra": True},
    UrlOpenInput.model_construct(url="file:///C:/Windows/test.exe"),
    UrlOpenInput(url="https://example.test").model_copy(update={"url": "file:///tmp/test"}),
])
def test_invalid_input_is_rejected_by_c1_before_provider_or_native_call(monkeypatch, windows_host, raw_input):
    provider = WindowsUrlOpenProvider()
    execute = AsyncMock(wraps=provider.execute)
    monkeypatch.setattr(provider, "execute", execute)
    with pytest.raises(ValidationError):
        asyncio.run(ToolRuntime(provider).execute("url.open", raw_input))
    execute.assert_not_called()
    windows_host.assert_not_called()


def test_direct_provider_reuses_contract_for_unvalidated_model_instances(windows_host):
    with pytest.raises(ValidationError):
        asyncio.run(WindowsUrlOpenProvider().execute("url.open", UrlOpenInput.model_construct(url="file:///tmp/test")))
    windows_host.assert_not_called()


@pytest.mark.parametrize("capability", [key for key in CAPABILITY_CATALOG if key != "url.open"] + ["open_url", "URL.OPEN", "url.open ", "unknown.foo"])
def test_provider_rejects_every_other_capability_without_native_invocation(windows_host, capability):
    with pytest.raises(KeyError) as error:
        asyncio.run(WindowsUrlOpenProvider().execute(capability, UrlOpenInput(url="https://example.test")))
    assert error.value.args == (capability,)
    windows_host.assert_not_called()


@pytest.mark.parametrize("failure", [OSError("native association failure"), PermissionError("native denied"), NotImplementedError("ShellExecute missing")])
def test_native_errors_propagate_the_same_exception_without_retry(windows_host, failure):
    windows_host.side_effect = failure
    with pytest.raises(type(failure)) as error:
        asyncio.run(runtime_with_provider().execute("url.open", {"url": "https://example.test"}))
    assert error.value is failure
    windows_host.assert_called_once_with("https://example.test/", "open")


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_non_windows_fails_closed_even_if_an_opener_attribute_exists(monkeypatch, native_opener, platform):
    monkeypatch.setattr(url_open, "sys", SimpleNamespace(platform=platform))
    with pytest.raises(OSError, match="requires a Windows host"):
        asyncio.run(runtime_with_provider().execute("url.open", {"url": "https://example.test"}))
    native_opener.assert_not_called()


def test_actual_host_with_only_native_boundary_mocked(native_opener):
    # Both CI jobs run this: real Windows platform, real non-Windows rejection.
    assert url_open.sys is sys and url_open.os is os
    if sys.platform == "win32":
        result = asyncio.run(runtime_with_provider().execute("url.open", {"url": "https://example.test"}))
        assert type(result) is NoDataOutput
        native_opener.assert_called_once_with("https://example.test/", "open")
    else:
        with pytest.raises(OSError, match="requires a Windows host"):
            asyncio.run(runtime_with_provider().execute("url.open", {"url": "https://example.test"}))
        native_opener.assert_not_called()


def test_native_call_uses_worker_thread_and_keeps_loop_responsive(windows_host):
    async def check():
        loop = asyncio.get_running_loop()
        loop_thread = threading.get_ident()
        entered = asyncio.Event()
        release = threading.Event()
        native_threads = []

        def open_url(*args):
            native_threads.append(threading.get_ident())
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(5), "Event loop did not release native worker"

        windows_host.side_effect = open_url
        task = asyncio.create_task(runtime_with_provider().execute("url.open", {"url": "https://example.test"}))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            assert not task.done()
            assert len(native_threads) == 1 and native_threads[0] != loop_thread
        finally:
            release.set()
            await task

    asyncio.run(check())
    windows_host.assert_called_once_with("https://example.test/", "open")


def test_only_explicit_registration_makes_url_open_available(windows_host):
    registry = CapabilityProviderRegistry()
    provider = WindowsUrlOpenProvider()
    assert registry.available_capabilities() == ()
    with pytest.raises(CapabilityUnavailableError):
        registry.resolve("url.open")
    registry.register("url.open", provider)
    assert registry.available_capabilities() == ("url.open",)
    assert registry.resolve("url.open") is provider
    for capability in CAPABILITY_CATALOG:
        if capability != "url.open":
            with pytest.raises(CapabilityUnavailableError):
                registry.resolve(capability)
    assert CapabilityProviderRegistry().available_capabilities() == ()
    windows_host.assert_not_called()
