from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import BaseTool, ToolContext, ToolResult, ToolSpec
from .providers import get_provider


CRITICAL_PROCESS_NAMES = {
    "launchd",
    "systemd",
    "init",
    "explorer.exe",
    "wininit.exe",
    "csrss.exe",
    "smss.exe",
    "system",
}
BLOCKED_SCHEDULER_COMMAND_PATTERNS = (
    r"(?i)\brm\s+-rf\b",
    r"(?i)\bformat\s+[a-z]:",
    r"(?i)\bmkfs\b",
    r"(?i)\bdel\s+/(s|q)\b",
    r"(?i)\bshutdown\b",
    r"(?i)\breboot\b",
)


def _allowed_roots(settings: dict[str, Any]) -> list[str]:
    roots = [str(path).strip() for path in settings.get("allowed_paths", []) if str(path).strip()]
    if roots:
        return roots
    return [str(Path.home())]


def _to_result(provider_result) -> ToolResult:
    if provider_result.success:
        return ToolResult(success=True, output=provider_result.output)
    return ToolResult(success=False, output="", error=provider_result.error or "Provider Fehler")


class FocusAppTool(BaseTool):
    spec = ToolSpec(
        tool_name="focus_app",
        risk_level="medium",
        requires_approval=True,
        input_schema={"app_name": "string"},
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        app_name = str(tool_input.get("app_name", "")).strip()
        if not app_name:
            return ToolResult(success=False, output="", error="app_name fehlt.")
        provider = get_provider()
        result = await provider.focus_app(app_name)
        return _to_result(result)


class CloseAppTool(BaseTool):
    spec = ToolSpec(
        tool_name="close_app",
        risk_level="high",
        requires_approval=True,
        input_schema={"app_name": "string"},
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        app_name = str(tool_input.get("app_name", "")).strip()
        if not app_name:
            return ToolResult(success=False, output="", error="app_name fehlt.")
        lowered = app_name.lower()
        if lowered in CRITICAL_PROCESS_NAMES:
            return ToolResult(success=False, output="", error=f"Systemkritische App blockiert: {app_name}")
        provider = get_provider()
        result = await provider.close_app(app_name)
        return _to_result(result)


class ListRunningAppsTool(BaseTool):
    spec = ToolSpec(
        tool_name="list_running_apps",
        risk_level="low",
        requires_approval=True,
        input_schema={"limit": "number"},
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        limit = int(tool_input.get("limit", 40) or 40)
        provider = get_provider()
        result = await provider.list_running_apps(limit=limit)
        return _to_result(result)


class ProcessListTool(BaseTool):
    spec = ToolSpec(
        tool_name="process_list",
        risk_level="low",
        requires_approval=True,
        input_schema={"limit": "number"},
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        limit = int(tool_input.get("limit", 25) or 25)
        provider = get_provider()
        result = await provider.process_list(limit=limit)
        return _to_result(result)


class ProcessTerminateTool(BaseTool):
    spec = ToolSpec(
        tool_name="process_terminate",
        risk_level="high",
        requires_approval=True,
        input_schema={"pid": "number", "name": "string", "force": "boolean"},
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        pid_raw = tool_input.get("pid")
        name = str(tool_input.get("name", "")).strip()
        force = str(tool_input.get("force", "false")).lower() in {"1", "true", "yes", "on"}

        pid: int | None = None
        if pid_raw is not None:
            try:
                pid = int(pid_raw)
            except (TypeError, ValueError):
                return ToolResult(success=False, output="", error="pid muss numerisch sein.")

        lowered = name.lower()
        if lowered in CRITICAL_PROCESS_NAMES:
            return ToolResult(success=False, output="", error=f"Systemkritischer Prozess blockiert: {name}")

        provider = get_provider()
        result = await provider.process_terminate(pid=pid, name=name or None, force=force)
        return _to_result(result)


class FileSearchTool(BaseTool):
    spec = ToolSpec(
        tool_name="file_search",
        risk_level="medium",
        requires_approval=True,
        input_schema={"query": "string", "limit": "number"},
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        query = str(tool_input.get("query", "")).strip()
        if not query:
            return ToolResult(success=False, output="", error="query fehlt.")
        limit = int(tool_input.get("limit", 20) or 20)
        provider = get_provider()
        result = await provider.file_search(
            query=query,
            roots=_allowed_roots(context.settings),
            limit=limit,
        )
        return _to_result(result)


class SendNotificationTool(BaseTool):
    spec = ToolSpec(
        tool_name="send_notification",
        risk_level="low",
        requires_approval=True,
        input_schema={"title": "string", "text": "string"},
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        title = str(tool_input.get("title", "Jarvis")).strip() or "Jarvis"
        text = str(tool_input.get("text", "")).strip()
        if not text:
            return ToolResult(success=False, output="", error="text fehlt.")
        provider = get_provider()
        result = await provider.send_notification(title=title, text=text)
        return _to_result(result)


class SchedulerCreateTaskTool(BaseTool):
    spec = ToolSpec(
        tool_name="scheduler_create_task",
        risk_level="high",
        requires_approval=True,
        input_schema={"task_name": "string", "time": "HH:MM", "command": "string"},
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        task_name = str(tool_input.get("task_name", "")).strip()
        time_label = str(tool_input.get("time", "")).strip()
        command = str(tool_input.get("command", "")).strip()

        if not task_name:
            return ToolResult(success=False, output="", error="task_name fehlt.")
        if not time_label:
            return ToolResult(success=False, output="", error="time fehlt.")
        if not command:
            return ToolResult(success=False, output="", error="command fehlt.")
        if len(command) > 220:
            return ToolResult(success=False, output="", error="command ist zu lang.")
        for pattern in BLOCKED_SCHEDULER_COMMAND_PATTERNS:
            if re.search(pattern, command):
                return ToolResult(success=False, output="", error="Unsicherer command blockiert.")

        provider = get_provider()
        result = await provider.scheduler_create_task(
            task_name=task_name,
            time_label=time_label,
            command=command,
        )
        return _to_result(result)
