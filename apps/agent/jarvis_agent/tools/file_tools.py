from __future__ import annotations

from pathlib import Path
from typing import Any

from ..safety import detect_dangerous_content, is_critical_path
from .base import BaseTool, ToolContext, ToolResult, ToolSpec
from .security import is_path_allowed, resolve_path


class FileReadTool(BaseTool):
    spec = ToolSpec(
        tool_name="file_read",
        risk_level="medium",
        requires_approval=True,
        input_schema={"path": "string"},
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        raw_path = str(tool_input.get("path", "")).strip()
        if not raw_path:
            return ToolResult(success=False, output="", error="path fehlt")

        target = resolve_path(raw_path)
        profile = context.profile or {}
        if is_critical_path(target, profile):
            return ToolResult(success=False, output="", error=f"Systemkritischer Pfad blockiert: {target}")

        allowed_paths = list(context.settings.get("allowed_paths", []))
        if not is_path_allowed(target, allowed_paths):
            return ToolResult(success=False, output="", error=f"Pfad nicht erlaubt: {target}")

        if not target.exists() or not target.is_file():
            return ToolResult(success=False, output="", error=f"Datei nicht gefunden: {target}")

        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = target.read_text(encoding="utf-8", errors="ignore")
        except Exception as error:
            return ToolResult(success=False, output="", error=str(error))

        if len(content) > 6000:
            content = content[:6000] + "\n...[gekürzt]"

        return ToolResult(success=True, output=content)


class FileWriteTool(BaseTool):
    spec = ToolSpec(
        tool_name="file_write",
        risk_level="high",
        requires_approval=True,
        input_schema={
            "path": "string",
            "content": "string",
            "mode": "string",
        },
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        raw_path = str(tool_input.get("path", "")).strip()
        content = str(tool_input.get("content", ""))
        mode = str(tool_input.get("mode", "overwrite")).strip().lower()

        if not raw_path:
            return ToolResult(success=False, output="", error="path fehlt")

        if mode not in {"overwrite", "append"}:
            return ToolResult(success=False, output="", error="mode muss overwrite oder append sein")

        target = resolve_path(raw_path)
        profile = context.profile or {}
        if is_critical_path(target, profile):
            return ToolResult(success=False, output="", error=f"Systemkritischer Pfad blockiert: {target}")

        dangerous_pattern = detect_dangerous_content(content, profile)
        if dangerous_pattern:
            return ToolResult(
                success=False,
                output="",
                error=f"Inhalt wegen Sicherheitsregel blockiert: {dangerous_pattern}",
            )

        allowed_paths = list(context.settings.get("allowed_paths", []))
        if not is_path_allowed(target, allowed_paths):
            return ToolResult(success=False, output="", error=f"Pfad nicht erlaubt: {target}")

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if mode == "append":
                with target.open("a", encoding="utf-8") as file_handle:
                    file_handle.write(content)
            else:
                target.write_text(content, encoding="utf-8")
        except Exception as error:
            return ToolResult(success=False, output="", error=str(error))

        size = 0
        try:
            size = Path(target).stat().st_size
        except Exception:
            pass

        return ToolResult(success=True, output=f"Datei geschrieben: {target} ({size} bytes)")
