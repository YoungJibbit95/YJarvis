"""The new descriptive inventory must not alter legacy identity or authority."""

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel, ValidationError

from jarvis_agent.domain import tool_inputs, tool_outputs
from jarvis_agent.domain.capability_catalog import (
    CAPABILITY_CATALOG, LEGACY_TOOL_CATALOG, LEGACY_TOOL_TO_CAPABILITY,
)
from jarvis_agent.tools import ToolRegistry
from jarvis_agent.tools.base import ToolResult
from test_turn_lifecycle import rig


EXPECTED_MAPPING = {
    "open_url": "url.open", "open_app": "apps.open",
    "raycast_open": "raycast.open", "raycast_run_command": "raycast.command.run",
    "clipboard_read": "clipboard.read", "clipboard_write": "clipboard.write",
    "reminder_create": "reminders.create", "reminder_list": "reminders.list",
    "calendar_create_event": "calendar.events.create", "calendar_list_events": "calendar.events.list",
    "notes_create": "notes.create", "notes_search": "notes.search",
    "mail_create_draft": "mail.drafts.create", "messages_send": "messages.send",
    "contacts_search": "contacts.search", "music_control": "music.control",
    "file_read": "files.read", "file_write": "files.write",
}


def test_semantic_catalog_and_legacy_view_share_exactly_eighteen_specs_bijectively():
    assert len(CAPABILITY_CATALOG) == len(LEGACY_TOOL_CATALOG) == len(LEGACY_TOOL_TO_CAPABILITY) == 18
    assert dict(LEGACY_TOOL_TO_CAPABILITY) == EXPECTED_MAPPING
    assert set(CAPABILITY_CATALOG) == set(EXPECTED_MAPPING.values())
    assert set(LEGACY_TOOL_CATALOG) == set(EXPECTED_MAPPING)
    assert len(set(LEGACY_TOOL_TO_CAPABILITY.values())) == 18
    assert len({id(spec) for spec in CAPABILITY_CATALOG.values()}) == 18
    assert {id(spec) for spec in CAPABILITY_CATALOG.values()} == {id(spec) for spec in LEGACY_TOOL_CATALOG.values()}
    for legacy_name, capability in EXPECTED_MAPPING.items():
        spec = CAPABILITY_CATALOG[capability]
        assert spec is LEGACY_TOOL_CATALOG[legacy_name]
        assert spec.capability == capability
        # Names are exact keys, not interchangeable aliases or inferred spelling.
        with pytest.raises(KeyError):
            CAPABILITY_CATALOG[legacy_name]
        with pytest.raises(KeyError):
            LEGACY_TOOL_CATALOG[capability]


@pytest.mark.parametrize("catalog, key", [
    (CAPABILITY_CATALOG, "apps.open"),
    (LEGACY_TOOL_CATALOG, "open_app"),
    (LEGACY_TOOL_TO_CAPABILITY, "open_app"),
])
def test_all_catalog_views_and_mapping_are_read_only(catalog, key):
    with pytest.raises(TypeError):
        catalog[key] = catalog[key]
    with pytest.raises(TypeError):
        del catalog[key]
    with pytest.raises(ValidationError, match="frozen"):
        CAPABILITY_CATALOG["apps.open"].capability = "apps.changed"


@pytest.mark.parametrize("key", ["unknown.capability", "open_app", "apps_open", "Apps.Open", " apps.open", "apps.open ", "calendar.create_event", "raycast.run_command"])
def test_semantic_lookup_has_no_fallback_or_name_conversion(key):
    with pytest.raises(KeyError) as error:
        CAPABILITY_CATALOG[key]
    assert error.value.args == (key,)


@pytest.mark.parametrize("key", ["unknown_tool", "apps.open", "Open_App", " open_app", "open_app ", "open.app"])
def test_legacy_mapping_and_view_do_not_guess_names(key):
    for mapping in (LEGACY_TOOL_TO_CAPABILITY, LEGACY_TOOL_CATALOG):
        with pytest.raises(KeyError) as error:
            mapping[key]
        assert error.value.args == (key,)


def test_catalog_covers_the_actual_registry_exactly_once():
    specs = ToolRegistry().list_specs()
    assert len(specs) == len(LEGACY_TOOL_CATALOG) == 18
    assert {s["tool_name"] for s in specs} == LEGACY_TOOL_CATALOG.keys()
    assert {name: spec.capability for name, spec in LEGACY_TOOL_CATALOG.items()} == EXPECTED_MAPPING
    assert len({spec.capability for spec in LEGACY_TOOL_CATALOG.values()}) == 18
    assert all(s["requires_approval"] is True for s in specs)
    assert all(set(s) == {"tool_name", "risk_level", "requires_approval", "input_schema"} for s in specs)
    assert all(not set(spec.capability.split(".")) & {"macos", "windows", "applescript", "powershell"}
               for spec in LEGACY_TOOL_CATALOG.values())


def test_catalog_is_immutable_and_unknown_names_are_not_guessed():
    with pytest.raises(TypeError):
        LEGACY_TOOL_CATALOG["invented_tool"] = LEGACY_TOOL_CATALOG["open_app"]
    with pytest.raises(ValidationError, match="frozen"):
        LEGACY_TOOL_CATALOG["open_app"].capability = "apps.changed"
    for name in ("invented_tool", "apps.open", " open_app", "Open_App"):
        with pytest.raises(KeyError):
            LEGACY_TOOL_CATALOG[name]


def test_deferred_metadata_does_not_pretend_to_be_an_available_typed_provider():
    for spec in LEGACY_TOOL_CATALOG.values():
        assert isinstance(spec.input_model, type) and issubclass(spec.input_model, BaseModel)
        assert isinstance(spec.output_model, type) and issubclass(spec.output_model, BaseModel)
        assert spec.reversible is spec.supports_dry_run is False
        assert spec.timeout_seconds == 30
        assert spec.idempotent == (spec.mode == "read")
        assert not hasattr(spec, "available")
    assert LEGACY_TOOL_CATALOG["raycast_run_command"].default_risk == "high"
    assert LEGACY_TOOL_CATALOG["raycast_run_command"].mode == "external_side_effect"
    assert LEGACY_TOOL_CATALOG["file_write"].idempotent is False  # Includes append.
    assert LEGACY_TOOL_CATALOG["music_control"].idempotent is False  # Includes next/previous.


def test_05b1_inputs_all_other_metadata_and_legacy_planner_specs_remain_unchanged():
    baseline = json.loads((Path(__file__).parent / "fixtures" / "tool_contract_baseline_05b1.json").read_text(encoding="utf-8"))
    actual = {}
    for name, spec in LEGACY_TOOL_CATALOG.items():
        data = spec.model_dump(exclude={"input_model", "output_model"})
        data["input_model"] = spec.input_model.__module__ + "." + spec.input_model.__qualname__
        actual[name] = data
    assert actual == baseline["catalog"]
    assert ToolRegistry().list_specs() == baseline["legacy_specs"]


def test_semantic_specs_preserve_accepted_metadata_and_exact_input_output_classes():
    fixtures = Path(__file__).parent / "fixtures"
    baseline = json.loads((fixtures / "tool_contract_baseline_05b1.json").read_text(encoding="utf-8"))
    outputs = json.loads((fixtures / "tool_outputs.json").read_text(encoding="utf-8"))
    for name, expected in baseline["catalog"].items():
        spec = CAPABILITY_CATALOG[expected["capability"]]
        assert spec.input_model is getattr(tool_inputs, expected["input_model"].rsplit(".", 1)[1])
        assert spec.output_model is getattr(tool_outputs, outputs[name]["model"])
        assert spec.model_dump(exclude={"input_model", "output_model"}) == {
            key: value for key, value in expected.items() if key != "input_model"
        }


@pytest.mark.parametrize("success, output, error", [(True, "App geoeffnet: Safari", None),
                                                 (False, "", "legacy error")])
def test_registry_returns_the_original_legacy_tool_result_without_output_conversion(monkeypatch, success, output, error):
    result = ToolResult(success=success, output=output, error=error)
    registry = ToolRegistry()
    execute = AsyncMock(return_value=result)
    monkeypatch.setattr(registry._tools["open_app"], "execute", execute)
    actual = asyncio.run(registry.execute("open_app", {"app_name": "Safari"}, {}, {}))
    assert actual is result
    assert asdict(actual) == {"success": success, "output": output, "error": error}
    # The legacy outcome and prose cannot masquerade as successful semantic data.
    with pytest.raises(ValidationError):
        LEGACY_TOOL_CATALOG["open_app"].output_model.model_validate(asdict(actual))


def test_registry_execution_and_planner_specs_remain_legacy(monkeypatch):
    registry = ToolRegistry()
    before = registry.list_specs()
    execute = AsyncMock(return_value=ToolResult(success=True, output="legacy result"))
    monkeypatch.setattr(registry._tools["open_app"], "execute", execute)
    tool_input, settings, profile = {"app_name": "Example"}, {"example": True}, {"name": "test"}

    async def check():
        result = await registry.execute("open_app", tool_input, settings, profile)
        assert result.output == "legacy result"
        execute.assert_awaited_once()
        args = execute.call_args.args
        assert args[0] is tool_input
        assert args[1].settings is settings and args[1].profile is profile
        assert not registry.has_tool(LEGACY_TOOL_CATALOG["open_app"].capability)
        rejected = await registry.execute("apps.open", tool_input, settings, profile)
        assert rejected.success is False
        assert rejected.error == "Tool nicht gefunden: apps.open"
        execute.assert_awaited_once()
    asyncio.run(check())
    assert registry.list_specs() == before
    assert next(s for s in before if s["tool_name"] == "raycast_run_command")["risk_level"] == "medium"


@pytest.mark.parametrize("payload, expected_text", [({"text": 123}, "123"), ({}, ""),
                                                  ({"text": "ok", "extra": True}, "ok")])
def test_real_legacy_tool_still_accepts_inputs_rejected_by_v2(monkeypatch, payload, expected_text):
    from jarvis_agent.tools import system_tools

    with pytest.raises(ValidationError):
        LEGACY_TOOL_CATALOG["clipboard_write"].input_model.model_validate(payload)
    command = AsyncMock(return_value=SimpleNamespace(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(system_tools, "run_command", command)
    # Real registry and tool, replacing only the native subprocess boundary.
    registry = ToolRegistry()
    specs = registry.list_specs()
    result = asyncio.run(registry.execute("clipboard_write", payload, {}, {}))
    assert result.success
    command.assert_awaited_once_with(["pbcopy"], input_text=expected_text)
    assert registry.list_specs() == specs


@pytest.mark.parametrize("legacy_name", EXPECTED_MAPPING)
def test_all_legacy_learned_tools_still_require_approval_with_legacy_wire_and_db_names(rig, legacy_name):
    async def check():
        await rig.db.upsert_learned_command(trigger="katalogaktion", tool_name=legacy_name, tool_input={})
        await rig.service.start_run("session", "run", "katalogaktion")
        pending = await rig.db.list_pending_approvals()
        assert len(pending) == 1
        assert pending[0]["tool_name"] == legacy_name
        assert (await rig.db.get_learned_command("katalogaktion"))["tool_name"] == legacy_name
        event = rig.events[-1]
        assert event["state"] == "approval_required"
        assert event["data"]["approval"]["tool_name"] == legacy_name
        assert event["data"]["approval"]["tool_input"] == {}
        rig.tools.execute.assert_not_awaited()
        rig.planner.assert_not_awaited()
    asyncio.run(check())
