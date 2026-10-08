"""Exact registry selection and composition with the accepted C1 kernel."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from jarvis_agent.domain import capability_catalog
from jarvis_agent.domain.capability_catalog import CAPABILITY_CATALOG
from jarvis_agent.domain.tool_inputs import AppOpenInput, ClipboardReadInput, ClipboardWriteInput
from jarvis_agent.domain.tool_outputs import ClipboardReadOutput, NoDataOutput
from jarvis_agent.provider_registry import CapabilityProviderRegistry, CapabilityUnavailableError
from jarvis_agent.tool_runtime import ToolProvider, ToolRuntime


def test_known_catalog_entries_are_unavailable_until_explicitly_registered():
    registry = CapabilityProviderRegistry()
    assert len(CAPABILITY_CATALOG) == 18
    assert registry.available_capabilities() == ()
    for capability in CAPABILITY_CATALOG:
        with pytest.raises(CapabilityUnavailableError) as error:
            registry.resolve(capability)
        assert error.value.capability == capability
        assert not isinstance(error.value, KeyError)


def test_availability_is_sorted_detached_and_local_to_each_registry():
    registry = CapabilityProviderRegistry()
    other = CapabilityProviderRegistry()
    provider = SimpleNamespace(execute=AsyncMock(return_value={}))
    registry.register("clipboard.write", provider)
    snapshot = registry.available_capabilities()
    registry.register("apps.open", provider)
    assert registry.available_capabilities() == ("apps.open", "clipboard.write")
    assert snapshot == ("clipboard.write",)
    assert isinstance(snapshot, tuple)
    assert other.available_capabilities() == ()
    provider.execute.assert_not_called()


def test_all_catalog_entries_can_be_registered_without_policy_or_platform_filtering():
    registry = CapabilityProviderRegistry()
    provider = SimpleNamespace(execute=AsyncMock())
    for capability in reversed(CAPABILITY_CATALOG):
        registry.register(capability, provider)
        assert registry.resolve(capability) is provider
    assert registry.available_capabilities() == tuple(sorted(CAPABILITY_CATALOG))
    provider.execute.assert_not_called()


@pytest.mark.parametrize("capability", [
    "unknown.foo", "open_app", "apps_open", "Apps.Open", " apps.open", "apps.open ",
    "calendar.create_event", "raycast.run_command",
])
def test_unknown_keys_fail_registration_lookup_and_execution_without_fallback(capability):
    registry = CapabilityProviderRegistry()
    provider = SimpleNamespace(execute=AsyncMock())
    registry.register("apps.open", provider)
    for operation in (
        lambda: registry.register(capability, provider),
        lambda: registry.resolve(capability),
        lambda: asyncio.run(registry.execute(capability, AppOpenInput(app_name="Example"))),
    ):
        with pytest.raises(KeyError) as error:
            operation()
        assert error.value.args == (capability,)
    assert registry.available_capabilities() == ("apps.open",)
    assert registry.resolve("apps.open") is provider
    provider.execute.assert_not_called()


@pytest.mark.parametrize("same_provider", [False, True])
def test_duplicate_registration_fails_without_replacing_the_first_provider(same_provider):
    registry = CapabilityProviderRegistry()
    original = SimpleNamespace(execute=AsyncMock())
    replacement = original if same_provider else SimpleNamespace(execute=AsyncMock())
    registry.register("apps.open", original)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("apps.open", replacement)
    assert registry.resolve("apps.open") is original
    assert registry.available_capabilities() == ("apps.open",)
    original.execute.assert_not_called()
    replacement.execute.assert_not_called()


def test_registry_delegates_exact_input_and_raw_output_once():
    registry = CapabilityProviderRegistry()
    raw_output = {"text": "Example"}
    provider = SimpleNamespace(execute=AsyncMock(return_value=raw_output))
    registry.register("clipboard.read", provider)
    input_data = ClipboardReadInput()
    actual = asyncio.run(registry.execute("clipboard.read", input_data))
    assert actual is raw_output
    provider.execute.assert_awaited_once_with("clipboard.read", input_data)
    assert provider.execute.call_args.args[1] is input_data


def test_runtime_selects_two_distinct_providers_and_keeps_typed_validation():
    registry = CapabilityProviderRegistry()
    read = SimpleNamespace(execute=AsyncMock(return_value={"text": "Example"}))
    write = SimpleNamespace(execute=AsyncMock(return_value={}))
    registry.register("clipboard.read", read)
    registry.register("clipboard.write", write)
    provider: ToolProvider = registry  # Structural composition; no C1 rewrite.
    runtime = ToolRuntime(provider)
    assert registry.resolve("clipboard.read") is read
    assert registry.resolve("clipboard.write") is write

    async def check():
        result = await runtime.execute("clipboard.read", {})
        assert type(result) is ClipboardReadOutput and result.text == "Example"
        assert type(read.execute.call_args.args[1]) is ClipboardReadInput
        write.execute.assert_not_called()
        result = await runtime.execute("clipboard.write", {"text": "  unchanged  "})
        assert type(result) is NoDataOutput and result.model_dump() == {}
        assert type(write.execute.call_args.args[1]) is ClipboardWriteInput
        assert write.execute.call_args.args[1].text == "  unchanged  "

    asyncio.run(check())
    read.execute.assert_awaited_once()
    write.execute.assert_awaited_once()


@pytest.mark.parametrize("registered", [False, True])
def test_invalid_input_never_enters_registry_execution_or_resolution(monkeypatch, registered):
    registry = CapabilityProviderRegistry()
    provider = SimpleNamespace(execute=AsyncMock())
    if registered:
        registry.register("clipboard.write", provider)
    execute = AsyncMock(wraps=registry.execute)
    resolve = Mock(wraps=registry.resolve)
    monkeypatch.setattr(registry, "execute", execute)
    monkeypatch.setattr(registry, "resolve", resolve)
    with pytest.raises(ValidationError):
        asyncio.run(ToolRuntime(registry).execute("clipboard.write", {"text": 123}))
    execute.assert_not_called()
    resolve.assert_not_called()
    provider.execute.assert_not_called()


@pytest.mark.parametrize("output", [None, {"text": 123}, {"success": True},
                                   ClipboardReadOutput.model_construct(text=123)])
def test_runtime_rejects_invalid_provider_output_through_registry(output):
    registry = CapabilityProviderRegistry()
    provider = SimpleNamespace(execute=AsyncMock(return_value=output))
    registry.register("clipboard.read", provider)
    with pytest.raises(ValidationError):
        asyncio.run(ToolRuntime(registry).execute("clipboard.read", {}))
    provider.execute.assert_awaited_once()


def test_unknown_and_unavailable_stay_distinct_through_runtime_and_never_fall_back():
    registry = CapabilityProviderRegistry()
    provider = SimpleNamespace(execute=AsyncMock())
    registry.register("clipboard.read", provider)
    with pytest.raises(CapabilityUnavailableError) as error:
        asyncio.run(ToolRuntime(registry).execute("apps.open", {"app_name": "Example"}))
    assert error.value.capability == "apps.open"
    with pytest.raises(KeyError) as error:
        asyncio.run(ToolRuntime(registry).execute("unknown.foo", {}))
    assert error.value.args == ("unknown.foo",)
    assert registry.available_capabilities() == ("clipboard.read",)
    provider.execute.assert_not_called()


@pytest.mark.parametrize("failure", [RuntimeError("provider failed"), TimeoutError("provider timeout"), asyncio.CancelledError()])
def test_provider_exception_identity_is_preserved_through_both_layers(failure):
    registry = CapabilityProviderRegistry()
    provider = SimpleNamespace(execute=AsyncMock(side_effect=failure))
    registry.register("clipboard.read", provider)
    with pytest.raises(type(failure)) as error:
        asyncio.run(ToolRuntime(registry).execute("clipboard.read", {}))
    assert error.value is failure
    provider.execute.assert_awaited_once()
    # A failure is not an implicit availability update or health/discovery result.
    assert registry.available_capabilities() == ("clipboard.read",)


def test_registration_resolution_and_runtime_do_not_consult_legacy_views(monkeypatch):
    class ForbiddenView:
        def __getitem__(self, key):
            raise AssertionError("Legacy lookup is forbidden")

    monkeypatch.setattr(capability_catalog, "LEGACY_TOOL_CATALOG", ForbiddenView())
    monkeypatch.setattr(capability_catalog, "LEGACY_TOOL_TO_CAPABILITY", ForbiddenView())
    registry = CapabilityProviderRegistry()
    provider = SimpleNamespace(execute=AsyncMock(return_value={}))
    registry.register("apps.open", provider)
    assert registry.resolve("apps.open") is provider
    assert registry.available_capabilities() == ("apps.open",)
    assert type(asyncio.run(ToolRuntime(registry).execute("apps.open", {"app_name": "Example"}))) is NoDataOutput
    provider.execute.assert_awaited_once()
