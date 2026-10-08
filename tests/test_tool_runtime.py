"""Semantic kernel contracts using only injected fake providers."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from jarvis_agent import tool_runtime
from jarvis_agent.domain import capability_catalog
from jarvis_agent.domain.capability_catalog import CAPABILITY_CATALOG
from jarvis_agent.domain.tool_inputs import ClipboardWriteInput
from jarvis_agent.domain.tool_outputs import ClipboardReadOutput, NoDataOutput
from jarvis_agent.tool_runtime import ToolRuntime
from test_turn_lifecycle import request_approval, rig


FIXTURES = Path(__file__).parent / "fixtures"
INPUTS = json.loads((FIXTURES / "tool_inputs.json").read_text(encoding="utf-8"))
OUTPUTS = json.loads((FIXTURES / "tool_outputs.json").read_text(encoding="utf-8"))
BASELINE = json.loads((FIXTURES / "tool_contract_baseline_05b1.json").read_text(encoding="utf-8"))
CASES = [(entry["capability"], INPUTS[name], OUTPUTS[name]["data"])
         for name, entry in BASELINE["catalog"].items()]


@pytest.mark.parametrize("capability, raw_input, raw_output", CASES, ids=[case[0] for case in CASES])
@pytest.mark.parametrize("model_instances", [False, True])
def test_all_semantic_capabilities_validate_both_boundaries_and_invoke_once(
    capability, raw_input, raw_output, model_instances,
):
    # Covers every mode/risk, including high-risk writes: metadata is not policy.
    spec = CAPABILITY_CATALOG[capability]
    expected_input = spec.input_model.model_validate(raw_input)
    expected_output = spec.output_model.model_validate(raw_output)
    provider = SimpleNamespace(execute=AsyncMock(return_value=expected_output if model_instances else raw_output))
    output = asyncio.run(ToolRuntime(provider).execute(capability, expected_input if model_instances else raw_input))
    provider.execute.assert_awaited_once()
    passed_capability, passed_input = provider.execute.call_args.args
    assert passed_capability == capability
    assert type(passed_input) is spec.input_model
    assert passed_input == expected_input
    assert type(output) is spec.output_model
    assert output == expected_output
    if spec.output_model is NoDataOutput:
        assert output.model_dump() == {}  # No success/approval/execution envelope.


@pytest.mark.parametrize("capability", [
    "unknown.capability", "open_app", "apps_open", "Apps.Open", " apps.open",
    "apps.open ", "calendar.create_event", "raycast.run_command",
])
def test_unknown_capabilities_have_no_alias_or_fallback_and_never_invoke_provider(capability):
    provider = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(KeyError) as error:
        asyncio.run(ToolRuntime(provider).execute(capability, {}))
    assert error.value.args == (capability,)
    provider.execute.assert_not_called()


@pytest.mark.parametrize("raw_input", [
    {}, {"text": 123}, {"text": "ok", "extra": True}, '{"text": "ok"}',
    ClipboardReadOutput(text="wrong model"),
    ClipboardWriteInput.model_construct(text=123),
    ClipboardWriteInput(text="ok").model_copy(update={"text": 123}),
])
def test_invalid_inputs_including_unvalidated_instances_never_invoke_provider(raw_input):
    provider = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(ValidationError):
        asyncio.run(ToolRuntime(provider).execute("clipboard.write", raw_input))
    provider.execute.assert_not_called()


@pytest.mark.parametrize("raw_output", [
    {}, None, {"text": 123}, {"text": "ok", "success": True}, '{"text": "ok"}',
    ClipboardWriteInput(text="wrong model"),
    ClipboardReadOutput.model_construct(text=123),
    ClipboardReadOutput(text="ok").model_copy(update={"text": 123}),
])
def test_invalid_outputs_are_validation_failures_after_one_invocation(raw_output):
    provider = SimpleNamespace(execute=AsyncMock(return_value=raw_output))
    with pytest.raises(ValidationError):
        asyncio.run(ToolRuntime(provider).execute("clipboard.read", {}))
    provider.execute.assert_awaited_once()


@pytest.mark.parametrize("raw_output", [None, {"success": True}, {"output": "App opened"}])
def test_no_data_output_rejects_missing_data_and_outcome_prose(raw_output):
    provider = SimpleNamespace(execute=AsyncMock(return_value=raw_output))
    with pytest.raises(ValidationError):
        asyncio.run(ToolRuntime(provider).execute("apps.open", {"app_name": "Example"}))
    provider.execute.assert_awaited_once()


@pytest.mark.parametrize("failure", [RuntimeError("provider failed"), TimeoutError("provider timeout"), asyncio.CancelledError()])
def test_provider_failures_propagate_the_same_exception_without_retry_or_normalization(failure):
    provider = SimpleNamespace(execute=AsyncMock(side_effect=failure))
    with pytest.raises(type(failure)) as error:
        asyncio.run(ToolRuntime(provider).execute("clipboard.read", {}))
    assert error.value is failure
    provider.execute.assert_awaited_once()


def test_provider_can_suspend_and_input_defaults_and_text_are_preserved():
    async def provide(capability, input_data):
        await asyncio.sleep(0)
        assert capability == "notes.search"
        assert input_data.query == "  Project  "
        assert input_data.limit == 8 and input_data.folder is None
        return {"titles": ["", "Repeated", "Repeated"]}

    provider = SimpleNamespace(execute=AsyncMock(side_effect=provide))
    output = asyncio.run(ToolRuntime(provider).execute("notes.search", {"query": "  Project  "}))
    assert output.titles == ("", "Repeated", "Repeated")
    provider.execute.assert_awaited_once()


def test_semantic_execution_does_not_consult_legacy_compatibility_views(monkeypatch):
    class ForbiddenView:
        def __getitem__(self, key):
            raise AssertionError("Legacy lookup is forbidden")

    monkeypatch.setattr(capability_catalog, "LEGACY_TOOL_CATALOG", ForbiddenView())
    monkeypatch.setattr(capability_catalog, "LEGACY_TOOL_TO_CAPABILITY", ForbiddenView())
    provider = SimpleNamespace(execute=AsyncMock(return_value={}))
    output = asyncio.run(ToolRuntime(provider).execute("apps.open", {"app_name": "Example"}))
    assert type(output) is NoDataOutput
    provider.execute.assert_awaited_once()


@pytest.mark.parametrize("missing", ["input_model", "output_model"])
def test_unmodeled_contract_is_rejected_before_provider_invocation(monkeypatch, missing):
    spec = CAPABILITY_CATALOG["clipboard.read"]
    spec = type(spec).model_validate(spec.model_dump() | {missing: None})
    monkeypatch.setattr(tool_runtime, "CAPABILITY_CATALOG", {spec.capability: spec})
    provider = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(TypeError, match="requires input and output contracts"):
        asyncio.run(ToolRuntime(provider).execute(spec.capability, {}))
    provider.execute.assert_not_called()


def test_legacy_approval_and_registry_execution_never_enter_v2(rig, monkeypatch):
    forbidden = AsyncMock(side_effect=AssertionError("Legacy execution entered V2"))
    monkeypatch.setattr(ToolRuntime, "execute", forbidden)

    async def check():
        approval_id = await request_approval(rig)
        assert await rig.service.handle_approval_decision(approval_id, "approve") == "approved"
        rig.tools.execute.assert_awaited_once()
        assert rig.tools.execute.call_args.kwargs["tool_name"] == "open_app"
        assert rig.tools.execute.call_args.kwargs["tool_input"] == {"app_name": "Safari"}
        assert rig.trace.index("db:resolve_approval") < rig.trace.index("tool:execute")

    asyncio.run(check())
    forbidden.assert_not_called()
