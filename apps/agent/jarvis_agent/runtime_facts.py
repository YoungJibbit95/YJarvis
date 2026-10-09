"""Exactly two read-only model tools backed by live runtime facts.

No legacy action is executable here. Known V2 specs are not provider wiring.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from typing import Any, Callable
import re

from .tools import ToolRegistry
from .tools.system_tools import (
    ClipboardReadTool, ClipboardWriteTool, OpenAppTool, OpenUrlTool,
    RaycastOpenTool, RaycastRunCommandTool,
)

# Backend prerequisites derived from the registered legacy implementation
# classes. Unknown future system tool classes intentionally fail closed.
_SYSTEM_COMMANDS: dict[type, str] = {
    OpenAppTool: "open",
    OpenUrlTool: "open",
    RaycastOpenTool: "open",
    RaycastRunCommandTool: "open",
    ClipboardReadTool: "pbpaste",
    ClipboardWriteTool: "pbcopy",
}

LOCAL_TIME_TOOL = "system.local_datetime"
DISCOVERY_TOOL = "toolkit.capability_snapshot"

TOOL_DESCRIPTIONS: tuple[tuple[str, str], ...] = (
    (LOCAL_TIME_TOOL,
     "Get the current LOCAL system date/time and UTC offset, not a generated or cached time. "
     "Use for current time, today's date and weekday questions."),
    (DISCOVERY_TOOL,
     "Inspect tools actually registered with this YJarvis process, their operating-system "
     "availability, required inputs, risk and approval rules. "
     "Use before claiming that Jarvis can perform a computer action."),
)


def required_live_fact_tool(message: str) -> str | None:
    """Conservative provenance gate; NEVER a Python-generated answer.

    Classify live-clock and current Toolkit availability inquiries broadly
    enough to withhold unverified model tokens. Normal conversation remains
    unclassified and streams without a tool-selection round.
    """
    lowered = re.sub(r"(?i)^\s*jarvis[\s,:;-]*", "", message.strip()).lower()

    clock_question = re.search(
        r"\b(?:wie\s+(?:spät|spaet)\s+(?:ist|haben)|"
        r"wie\s+(?:viel|viele)\s+uhr|"
        r"welches?\s+datum(?:\s+(?:haben|ist))?|"
        r"welcher\s+tag\s+ist\s+heute)\b",
        lowered,
    )
    current_word = re.search(
        r"\b(?:aktuell(?:e|en|er|es)?|heute|heutig(?:e|en|er|es)?|"
        r"jetzt|gerade|momentan|lokal(?:e|en|er|es)?)\b",
        lowered,
    )
    clock_subject = re.search(r"\b(?:uhr(?:zeit)?|zeit|datum|tag)\b", lowered)
    if clock_question or (current_word and clock_subject):
        return LOCAL_TIME_TOOL

    if re.search(r"\bwas\s+kannst\s+du\b", lowered):
        return DISCOVERY_TOOL
    subject = re.search(
        r"\b(?:toolkit|systemfunktionen|systemfähigkeiten|systemfaehigkeiten|"
        r"funktionen|fähigkeiten|faehigkeiten|tools|werkzeuge|"
        r"programme|programmen|anwendungen|apps|möglichkeiten|moeglichkeiten)\b",
        lowered,
    )
    local_context = re.search(
        r"\b(?:du|dir|dein(?:e|em|en|er|es)?|hier|dies(?:em|en|er|es)|"
        r"rechner|computer|pc|betriebssystem|system|verfügbar|verfuegbar|"
        r"installiert|nutzen|benutzen|verwenden|bedienen|bedienst|"
        r"unterstützt|unterstuetzt|kannst|kann|stehen|zur\s+verfügung|"
        r"zur\s+verfuegung)\b",
        lowered,
    )
    if subject and local_context:
        return DISCOVERY_TOOL
    return None


class ReadOnlyToolkit:
    """An explicitly closed, side-effect-free dispatcher, never ToolRegistry.execute."""

    def __init__(
        self,
        tools: ToolRegistry | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        platform_name: str | None = None,
        command_exists: Callable[[str], str | None] = shutil.which,
    ) -> None:
        self._tools = tools
        self._clock = clock if clock is not None else lambda: datetime.now().astimezone()
        self._platform = platform_name if platform_name is not None else sys.platform
        self._command_exists = command_exists

    def descriptions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object", "properties": {},
                        "required": [], "additionalProperties": False,
                    },
                },
            }
            for name, description in TOOL_DESCRIPTIONS
        ]

    def execute(self, name: str, arguments: Any, *, settings: dict[str, Any]) -> dict[str, Any]:
        # Explicit exception to legacy Approval only for these two *exact*
        # side-effect-free operations, with no accepted arguments.
        if type(arguments) is not dict or arguments:
            raise ValueError("Nur leere Argumente fuer read-only Toolkit-Fakten erlaubt")
        if name == LOCAL_TIME_TOOL:
            return self.local_datetime()
        if name == DISCOVERY_TOOL:
            return self.capability_snapshot(settings=settings)
        raise ValueError("Nicht registrierte read-only Funktion")

    def local_datetime(self) -> dict[str, Any]:
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Systemzeit besitzt keine verifizierbare Zeitzone")
        offset = now.strftime("%z")
        if len(offset) != 5:
            raise ValueError("UTC-Offset ungueltig")
        return {
            "capability": LOCAL_TIME_TOOL,
            "local_iso": now.isoformat(timespec="seconds"),
            "local_date": now.date().isoformat(),
            "weekday_iso": now.isoweekday(),
            "timezone_identifier": getattr(now.tzinfo, "key", None),
            "timezone_label": now.tzname(),
            "utc_offset": f"{offset[:3]}:{offset[3:]}",
            "source": "datetime.now().astimezone() system clock",
            "notes": "OS-local clock; timezone label may not be an IANA identifier",
        }

    def _legacy_runtime_status(self, tool_name: str, settings: dict[str, Any]) -> dict[str, Any]:
        if self._tools is None:
            return {"platform_supported": False, "available": False, "availability_note": "No active legacy registry"}
        # The registry owns its instances. No other global capability list
        # is used as proof of executable tools.
        registered = self._tools._tools.get(tool_name)
        if registered is None:
            return {"platform_supported": False, "available": False, "availability_note": "Not registered"}
        module = type(registered).__module__
        if module.endswith(".applescript_tools"):
            supported = self._platform == "darwin"
            return {
                "platform_supported": supported,
                "available": supported and bool(self._command_exists("osascript")),
                "availability_note": "macOS AppleScript; target app and OS permissions not probed",
            }
        if module.endswith(".system_tools"):
            command = _SYSTEM_COMMANDS.get(type(registered))
            supported = self._platform == "darwin" and command is not None
            available = supported and bool(self._command_exists(command))
            return {
                "platform_supported": supported,
                "available": available,
                "backend_requirement": command,
                "availability_note": (
                    f"macOS backend requires {command}; target app and OS permissions not probed"
                    if command else "Unknown macOS backend requirement; fail closed"
                ),
            }
        if module.endswith(".file_tools"):
            configured = settings.get("allowed_paths", [])
            enabled = isinstance(configured, list) and any(
                isinstance(p, str) and p.strip() for p in configured
            )
            return {
                "platform_supported": True,
                "available": enabled,
                "availability_note": (
                    "Python file backend; specific path still needs allowlist/safety/approval"
                    if enabled else "No allowed paths configured; cannot access files"
                ),
            }
        return {
            "platform_supported": False,
            "available": False,
            "availability_note": "Unknown provider implementation; fail closed",
        }

    def capability_snapshot(self, *, settings: dict[str, Any]) -> dict[str, Any]:
        # The V2 domain catalog and provider registry intentionally cannot be
        # imported into the active legacy runtime (domain-isolation contract).
        # Registered legacy tool instances remain the only executable evidence.
        legacy: list[dict[str, Any]] = []
        if self._tools is not None:
            for spec in self._tools.list_specs():
                name = spec["tool_name"]
                availability = self._legacy_runtime_status(name, settings)
                legacy.append({
                    "name": name,
                    "registered": True,
                    **availability,
                    "risk": spec["risk_level"],
                    "requires_approval": spec["requires_approval"],
                    "approved": False,
                    "input_fields": sorted(spec["input_schema"]),
                })

        # No CapabilityProviderRegistry instance is wired to this production
        # TurnEngine. Specs in CAPABILITY_CATALOG are known, NOT executable.
        # No production V2 ToolRuntime or provider registry is wired, so the
        # independent V2 catalog is NOT enumerated as live capability data.
        known_v2: list[str] = []
        runtime = [
            {
                "name": name,
                "registered": True,
                "available": True,
                "requires_approval": False,
                "risk": "read_only",
                "input_fields": [],
                "source": "ReadOnlyToolkit.execute (exact-name dispatch)",
            }
            for name, _ in TOOL_DESCRIPTIONS
        ]
        return {
            "platform": self._platform,
            "read_only_runtime": runtime,
            "legacy_registered": legacy,
            "v2_catalog": {
                "known_capabilities": known_v2,
                "provider_wired_to_current_agent": False,
                "available_for_execution": [],
                "catalog_enumerated": False,
                "note": (
                    "Separate V2 specification catalog exists but is not imported "
                    "into legacy runtime or wired for execution"
                ),
            },
            "discovery_does_not_grant_approval": True,
            "note": "Availability is platform/backend readiness, not target app or permission verification",
        }
