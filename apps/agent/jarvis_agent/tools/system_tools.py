from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .base import BaseTool, ToolContext, ToolResult, ToolSpec, run_command


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
        app_name = str(tool_input.get("app_name", "")).strip()
        if not app_name:
            return ToolResult(success=False, output="", error="app_name fehlt.")

        process = await run_command(["open", "-a", app_name])
        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "App konnte nicht geoeffnet werden")

        return ToolResult(success=True, output=f"App geoeffnet: {app_name}")


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
