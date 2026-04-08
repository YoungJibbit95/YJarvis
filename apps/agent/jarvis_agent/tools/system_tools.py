from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse
from urllib.parse import quote

from ..app_aliases import normalize_app_name
from .base import BaseTool, ToolContext, ToolResult, ToolSpec, run_command


RAYCAST_SEGMENT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,120}$")


class OpenUrlTool(BaseTool):
    spec = ToolSpec(
        tool_name="open_url",
        risk_level="medium",
        requires_approval=True,
        input_schema={"url": "string"},
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        url = str(tool_input.get("url", "")).strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return ToolResult(success=False, output="", error="Nur http/https URLs sind erlaubt.")

        process = await run_command(["open", url])
        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "open fehlgeschlagen")

        return ToolResult(success=True, output=f"URL geoeffnet: {url}")


class OpenAppTool(BaseTool):
    spec = ToolSpec(
        tool_name="open_app",
        risk_level="medium",
        requires_approval=True,
        input_schema={"app_name": "string"},
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        raw_app_name = str(tool_input.get("app_name", "")).strip()
        app_name = normalize_app_name(raw_app_name)
        if not app_name:
            return ToolResult(success=False, output="", error="app_name fehlt.")

        process = await run_command(["open", "-a", app_name])
        if process.returncode != 0 and raw_app_name and raw_app_name != app_name:
            fallback_process = await run_command(["open", "-a", raw_app_name])
            if fallback_process.returncode == 0:
                return ToolResult(success=True, output=f"App geoeffnet: {raw_app_name}")

        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "App konnte nicht geoeffnet werden")

        return ToolResult(success=True, output=f"App geoeffnet: {app_name}")


class RaycastOpenTool(BaseTool):
    spec = ToolSpec(
        tool_name="raycast_open",
        risk_level="low",
        requires_approval=True,
        input_schema={"fallback_text": "string"},
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        fallback_text = str(tool_input.get("fallback_text", "")).strip()
        if not fallback_text:
            process = await run_command(["open", "-a", "Raycast"])
            if process.returncode != 0:
                return ToolResult(success=False, output="", error=process.stderr.strip() or "Raycast konnte nicht gestartet werden")
            return ToolResult(success=True, output="Raycast geoeffnet.")

        encoded = quote(fallback_text, safe="")
        deeplink = f"raycast://extensions/raycast/raycast/navigation-search?fallbackText={encoded}"
        process = await run_command(["open", "-g", deeplink])
        if process.returncode == 0:
            return ToolResult(success=True, output=f"Raycast Suche geoeffnet: {fallback_text}")

        fallback_process = await run_command(["open", "-a", "Raycast"])
        if fallback_process.returncode != 0:
            return ToolResult(
                success=False,
                output="",
                error=(
                    process.stderr.strip()
                    or fallback_process.stderr.strip()
                    or "Raycast Deeplink fehlgeschlagen"
                ),
            )

        return ToolResult(
            success=True,
            output=f"Raycast gestartet. Deeplink-Suche war nicht verfuegbar ({fallback_text}).",
        )


class RaycastRunCommandTool(BaseTool):
    spec = ToolSpec(
        tool_name="raycast_run_command",
        risk_level="medium",
        requires_approval=True,
        input_schema={
            "owner": "string",
            "extension": "string",
            "command": "string",
            "fallback_text": "string",
            "background": "boolean",
        },
    )

    def _valid_segment(self, value: str) -> bool:
        return bool(RAYCAST_SEGMENT_RE.match(value))

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        owner = str(tool_input.get("owner", "")).strip()
        extension = str(tool_input.get("extension", "")).strip()
        command = str(tool_input.get("command", "")).strip()
        fallback_text = str(tool_input.get("fallback_text", "")).strip()
        background_raw = tool_input.get("background", True)
        background = str(background_raw).strip().lower() not in {"0", "false", "no", "off"}

        if not owner or not self._valid_segment(owner):
            return ToolResult(success=False, output="", error="owner ist ungueltig.")
        if not extension or not self._valid_segment(extension):
            return ToolResult(success=False, output="", error="extension ist ungueltig.")
        if not command or not self._valid_segment(command):
            return ToolResult(success=False, output="", error="command ist ungueltig.")

        deeplink = f"raycast://extensions/{owner}/{extension}/{command}"
        if fallback_text:
            deeplink += f"?fallbackText={quote(fallback_text, safe='')}"

        args = ["open"]
        if background:
            args.append("-g")
        args.append(deeplink)

        process = await run_command(args)
        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "Raycast Deeplink fehlgeschlagen")

        return ToolResult(
            success=True,
            output=f"Raycast Command ausgefuehrt: {owner}/{extension}/{command}",
        )


class ClipboardReadTool(BaseTool):
    spec = ToolSpec(
        tool_name="clipboard_read",
        risk_level="low",
        requires_approval=True,
        input_schema={},
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        process = await run_command(["pbpaste"])
        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "pbpaste fehlgeschlagen")
        return ToolResult(success=True, output=process.stdout.strip())


class ClipboardWriteTool(BaseTool):
    spec = ToolSpec(
        tool_name="clipboard_write",
        risk_level="medium",
        requires_approval=True,
        input_schema={"text": "string"},
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        text = str(tool_input.get("text", ""))
        process = await run_command(["pbcopy"], input_text=text)
        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "pbcopy fehlgeschlagen")
        return ToolResult(success=True, output="Zwischenablage aktualisiert.")
