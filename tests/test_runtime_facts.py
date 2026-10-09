"""YJCOM-03: OS facts and capability discovery are real, bounded and read-only."""
import asyncio
from datetime import datetime, timedelta, tzinfo
from unittest.mock import AsyncMock

import pytest

from jarvis_agent.domain.capability_catalog import CAPABILITY_CATALOG
from jarvis_agent.runtime_facts import (
    DISCOVERY_TOOL, LOCAL_TIME_TOOL, ReadOnlyToolkit, required_live_fact_tool,
)
from jarvis_agent.tools import ToolRegistry


class FakeBerlinTZ(tzinfo):
    key = "Europe/Berlin"

    def utcoffset(self, dt):
        return timedelta(hours=2)

    def dst(self, dt):
        return timedelta(0)

    def tzname(self, dt):
        return "CEST"


FROZEN = datetime(2026, 10, 9, 17, 23, 5, tzinfo=FakeBerlinTZ())


def test_local_datetime_has_verifiable_frozen_clock_and_zone():
    toolkit = ReadOnlyToolkit(clock=lambda: FROZEN, platform_name="win32")
    facts = toolkit.execute(LOCAL_TIME_TOOL, {}, settings={})
    assert facts["local_iso"] == "2026-10-09T17:23:05+02:00"
    assert facts["local_date"] == "2026-10-09"
    assert facts["weekday_iso"] == 5
    assert facts["timezone_identifier"] == "Europe/Berlin"
    assert facts["timezone_label"] == "CEST"
    assert facts["utc_offset"] == "+02:00"
    assert "system clock" in facts["source"]
    assert facts["capability"] == LOCAL_TIME_TOOL


def test_system_clock_must_be_aware():
    toolkit = ReadOnlyToolkit(clock=lambda: datetime(2026, 10, 9))
    with pytest.raises(ValueError, match="Zeitzone"):
        toolkit.execute(LOCAL_TIME_TOOL, {}, settings={})


@pytest.mark.parametrize("name,args", [
    ("unknown.run", {}),
    ("open_app", {}),
    ("file_write", {}),
    (LOCAL_TIME_TOOL, {"path": "/tmp"}),
    (DISCOVERY_TOOL, {"execute": True}),
    (LOCAL_TIME_TOOL, []),
    (LOCAL_TIME_TOOL, None),
])
def test_readonly_dispatcher_is_closed_and_never_executes_legacy(name, args):
    registry = ToolRegistry()
    registry.execute = AsyncMock(side_effect=AssertionError("Must not execute legacy tools"))
    toolkit = ReadOnlyToolkit(registry, clock=lambda: FROZEN, platform_name="darwin")
    with pytest.raises(ValueError):
        toolkit.execute(name, args, settings={})
    registry.execute.assert_not_awaited()


def test_offered_tool_schema_is_two_empty_argument_readonly_functions():
    tools = ReadOnlyToolkit().descriptions()
    assert {item["function"]["name"] for item in tools} == {LOCAL_TIME_TOOL, DISCOVERY_TOOL}
    assert all(item["type"] == "function" for item in tools)
    assert all(item["function"]["parameters"] == {
        "type": "object", "properties": {}, "required": [], "additionalProperties": False,
    } for item in tools)


def test_capability_snapshot_distinguishes_actual_registry_and_unknown_platform():
    registry = ToolRegistry()
    registry.execute = AsyncMock(side_effect=AssertionError("Discovery never runs a tool"))
    clock = lambda: FROZEN
    windows = ReadOnlyToolkit(registry, clock=clock, platform_name="win32",
                              command_exists=lambda command: None)
    snap = windows.execute(DISCOVERY_TOOL, {}, settings={"allowed_paths": []})
    assert snap["platform"] == "win32"
    assert {entry["name"] for entry in snap["legacy_registered"]} == {
        spec["tool_name"] for spec in registry.list_specs()
    }
    apps = next(item for item in snap["legacy_registered"] if item["name"] == "open_app")
    notes = next(item for item in snap["legacy_registered"] if item["name"] == "notes_search")
    files = next(item for item in snap["legacy_registered"] if item["name"] == "file_read")
    assert apps["registered"] and not apps["available"] and not apps["platform_supported"]
    assert notes["registered"] and not notes["available"]
    assert files["platform_supported"] and not files["available"]
    assert apps["requires_approval"] and not apps["approved"]
    assert snap["v2_catalog"]["known_capabilities"] == []
    assert not snap["v2_catalog"]["catalog_enumerated"]
    assert "notes.search" in CAPABILITY_CATALOG  # independently known, not live
    assert snap["v2_catalog"]["available_for_execution"] == []
    assert not snap["v2_catalog"]["provider_wired_to_current_agent"]
    assert {x["name"] for x in snap["read_only_runtime"]} == {LOCAL_TIME_TOOL, DISCOVERY_TOOL}
    assert all(x["available"] and not x["requires_approval"] for x in snap["read_only_runtime"])
    registry.execute.assert_not_awaited()


def test_snapshot_uses_runtime_and_actual_command_availability_not_catalog_promise():
    toolkit = ReadOnlyToolkit(
        ToolRegistry(), platform_name="darwin",
        command_exists=lambda command: "/usr/bin/" + command if command in {"open", "osascript"} else None,
    )
    data = toolkit.capability_snapshot(settings={"allowed_paths": ["/tmp/project"]})
    registered = {row["name"]: row for row in data["legacy_registered"]}
    assert registered["open_app"]["available"]
    assert registered["open_app"]["backend_requirement"] == "open"
    assert registered["reminder_list"]["available"]
    assert registered["clipboard_read"]["backend_requirement"] == "pbpaste"
    assert not registered["clipboard_read"]["available"]
    assert registered["clipboard_write"]["backend_requirement"] == "pbcopy"
    assert not registered["clipboard_write"]["available"]
    assert "target app and OS permissions not probed" in registered["open_app"]["availability_note"]
    assert registered["file_read"]["available"]
    assert registered["file_read"]["requires_approval"]
    assert "notes.search" in CAPABILITY_CATALOG
    assert "notes.search" not in data["v2_catalog"]["available_for_execution"]
    assert data["v2_catalog"]["available_for_execution"] == []
    unavailable = ReadOnlyToolkit(
        ToolRegistry(), platform_name="darwin", command_exists=lambda command: None,
    ).capability_snapshot(settings={})
    assert not next(item for item in unavailable["legacy_registered"]
                    if item["name"] == "reminder_list")["available"]


@pytest.mark.parametrize("text,name", [
    ("Jarvis, wie spät ist es?", LOCAL_TIME_TOOL),
    ("Wie viel Uhr haben wir?", LOCAL_TIME_TOOL),
    ("Welches Datum haben wir?", LOCAL_TIME_TOOL),
    ("Was kannst du?", DISCOVERY_TOOL),
    ("Welche Systemfunktionen kannst du gerade verwenden?", DISCOVERY_TOOL),
    ("Welche Funktionen hast du?", DISCOVERY_TOOL),
    ("Welche Programme kannst du auf diesem Rechner tatsächlich bedienen?", DISCOVERY_TOOL),
    ("Welche Anwendungen stehen dir hier zur Verfügung?", DISCOVERY_TOOL),
    ("Was kann dein Toolkit auf diesem Betriebssystem?", DISCOVERY_TOOL),
    ("Sag mir die aktuelle lokale Uhrzeit.", LOCAL_TIME_TOOL),
    ("Wie viel Uhr ist gerade auf meinem PC?", LOCAL_TIME_TOOL),
    ("Kannst du mir sagen, welche Apps hier verfügbar sind?", DISCOVERY_TOOL),
    ("Was unterstützt dein Toolkit?", DISCOVERY_TOOL),
    ("Welche Programme sind hier installiert?", DISCOVERY_TOOL),
    ("Hallo, Jarvis", None),
    ("Danke, Jarvis", None),
    ("Warum ist Zeit relativ?", None),
    ("Erklär mir das Datum der Französischen Revolution.", None),
])
def test_live_fact_guard_prevents_fabricated_time_without_canned_answers(text, name):
    assert required_live_fact_tool(text) == name


@pytest.mark.parametrize("available_commands,read_expected,write_expected", [
    ({"open"}, False, False),
    ({"open", "pbpaste"}, True, False),
    ({"open", "pbcopy"}, False, True),
    ({"open", "pbpaste", "pbcopy"}, True, True),
    (set(), False, False),
])
def test_clipboard_availability_checks_actual_backend_binary(
    available_commands, read_expected, write_expected,
):
    registry = ToolRegistry()
    registry.execute = AsyncMock(side_effect=AssertionError("Discovery cannot execute"))
    consulted = []

    def which(command):
        consulted.append(command)
        return "/usr/bin/" + command if command in available_commands else None

    toolkit = ReadOnlyToolkit(registry, platform_name="darwin", command_exists=which)
    rows = {row["name"]: row for row in toolkit.capability_snapshot(settings={})["legacy_registered"]}
    assert rows["open_app"]["available"] == ("open" in available_commands)
    assert rows["open_url"]["available"] == ("open" in available_commands)
    assert rows["clipboard_read"]["available"] is read_expected
    assert rows["clipboard_write"]["available"] is write_expected
    assert rows["clipboard_read"]["backend_requirement"] == "pbpaste"
    assert rows["clipboard_write"]["backend_requirement"] == "pbcopy"
    assert "OS permissions not probed" in rows["clipboard_read"]["availability_note"]
    assert "target app and OS permissions not probed" in rows["open_url"]["availability_note"]
    assert "pbpaste" in consulted and "pbcopy" in consulted
    registry.execute.assert_not_awaited()


def test_windows_clipboard_and_mac_only_tools_are_never_advertised_available():
    checked = []

    def which(command):
        checked.append(command)
        return "C:/fake/" + command

    registry = ToolRegistry()
    registry.execute = AsyncMock(side_effect=AssertionError("Discovery cannot execute"))
    toolkit = ReadOnlyToolkit(registry, platform_name="win32", command_exists=which)
    rows = {row["name"]: row for row in toolkit.capability_snapshot(settings={})["legacy_registered"]}
    for name in ("clipboard_read", "clipboard_write", "open_url", "open_app",
                 "raycast_open", "reminder_list", "notes_search"):
        assert rows[name]["registered"] and rows[name]["requires_approval"]
        assert not rows[name]["platform_supported"]
        assert not rows[name]["available"]
    assert checked == []
    registry.execute.assert_not_awaited()
