from __future__ import annotations

from typing import Any

from .applescript_tools import (
    CalendarCreateEventTool,
    CalendarListEventsTool,
    ContactsSearchTool,
    MailCreateDraftTool,
    MessagesSendTool,
    MusicControlTool,
    NotesCreateTool,
    NotesSearchTool,
    ReminderCreateTool,
    ReminderListTool,
)
from .base import BaseTool, ToolContext, ToolResult
from .file_tools import FileReadTool, FileWriteTool
from .system_tools import (
    ClipboardReadTool,
    ClipboardWriteTool,
    OpenAppTool,
    OpenUrlTool,
    RaycastOpenTool,
    RaycastRunCommandTool,
)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._register(OpenUrlTool())
        self._register(OpenAppTool())
        self._register(RaycastOpenTool())
        self._register(RaycastRunCommandTool())
        self._register(ClipboardReadTool())
        self._register(ClipboardWriteTool())
        self._register(ReminderCreateTool())
        self._register(ReminderListTool())
        self._register(CalendarCreateEventTool())
        self._register(CalendarListEventsTool())
        self._register(NotesCreateTool())
        self._register(NotesSearchTool())
        self._register(MailCreateDraftTool())
        self._register(MessagesSendTool())
        self._register(ContactsSearchTool())
        self._register(MusicControlTool())
        self._register(FileReadTool())
        self._register(FileWriteTool())

    def _register(self, tool: BaseTool) -> None:
        self._tools[tool.spec.tool_name] = tool

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def list_specs(self) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        for tool in self._tools.values():
            specs.append(
                {
                    "tool_name": tool.spec.tool_name,
                    "risk_level": tool.spec.risk_level,
                    "requires_approval": tool.spec.requires_approval,
                    "input_schema": tool.spec.input_schema,
                }
            )
        return specs

    async def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        settings: dict[str, Any],
        profile: dict[str, Any] | None = None,
    ) -> ToolResult:
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolResult(success=False, output="", error=f"Tool nicht gefunden: {tool_name}")

        context = ToolContext(settings=settings, profile=profile)
        return await tool.execute(tool_input, context)
