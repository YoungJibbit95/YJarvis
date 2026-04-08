from __future__ import annotations

from datetime import datetime
from typing import Any

from .base import BaseTool, ToolContext, ToolResult, ToolSpec, run_command


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class ReminderCreateTool(BaseTool):
    spec = ToolSpec(
        tool_name="reminder_create",
        risk_level="medium",
        requires_approval=True,
        input_schema={"title": "string", "notes": "string", "due_at": "string (ISO datetime)"},
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        title = str(tool_input.get("title", "")).strip()
        notes = str(tool_input.get("notes", "")).strip()
        due_at_raw = str(tool_input.get("due_at", "")).strip()

        if not title:
            return ToolResult(success=False, output="", error="title fehlt")

        due_at: datetime | None = None
        if due_at_raw:
            try:
                due_at = datetime.fromisoformat(due_at_raw.replace("Z", "+00:00"))
            except ValueError:
                return ToolResult(success=False, output="", error="due_at muss ISO-Format haben (z. B. 2026-04-09T10:00)")

            if due_at.tzinfo is not None:
                due_at = due_at.astimezone().replace(tzinfo=None)

        title_escaped = _escape(title)
        notes_escaped = _escape(notes)

        properties_parts = [f'name:"{title_escaped}"']
        if notes:
            properties_parts.append(f'body:"{notes_escaped}"')
        if due_at is not None:
            properties_parts.append("due date:dueDate")
        properties = "{" + ", ".join(properties_parts) + "}"

        script_lines = ['tell application "Reminders"']
        if due_at is not None:
            script_lines.extend(
                [
                    "    set dueDate to current date",
                    f"    set year of dueDate to {due_at.year}",
                    f"    set month of dueDate to {due_at.month}",
                    f"    set day of dueDate to {due_at.day}",
                    f"    set hours of dueDate to {due_at.hour}",
                    f"    set minutes of dueDate to {due_at.minute}",
                    f"    set seconds of dueDate to {due_at.second}",
                ]
            )
        script_lines.extend(
            [
                "    tell default list",
                f"        make new reminder with properties {properties}",
                "    end tell",
                "end tell",
            ]
        )
        script = "\n".join(script_lines)

        process = await run_command(["osascript", "-e", script])
        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "AppleScript Fehler")

        if due_at is None:
            return ToolResult(success=True, output=f"Erinnerung erstellt: {title}")

        due_label = due_at.strftime("%Y-%m-%d %H:%M")
        return ToolResult(success=True, output=f"Erinnerung erstellt: {title} (faellig {due_label})")


class CalendarCreateEventTool(BaseTool):
    spec = ToolSpec(
        tool_name="calendar_create_event",
        risk_level="medium",
        requires_approval=True,
        input_schema={
            "title": "string",
            "start_at": "string (ISO datetime)",
            "start_offset_minutes": "number",
            "duration_minutes": "number",
        },
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        title = str(tool_input.get("title", "")).strip()
        if not title:
            return ToolResult(success=False, output="", error="title fehlt")

        start_at_raw = str(tool_input.get("start_at", "")).strip()

        try:
            start_offset_minutes = int(tool_input.get("start_offset_minutes", 5))
        except (TypeError, ValueError):
            return ToolResult(success=False, output="", error="start_offset_minutes muss eine Zahl sein")

        try:
            duration_minutes = int(tool_input.get("duration_minutes", 60))
        except (TypeError, ValueError):
            return ToolResult(success=False, output="", error="duration_minutes muss eine Zahl sein")

        if duration_minutes < 1 or duration_minutes > 24 * 60:
            return ToolResult(success=False, output="", error="duration_minutes muss zwischen 1 und 1440 liegen")

        start_at: datetime | None = None
        if start_at_raw:
            try:
                start_at = datetime.fromisoformat(start_at_raw.replace("Z", "+00:00"))
            except ValueError:
                return ToolResult(success=False, output="", error="start_at muss ISO-Format haben (z. B. 2026-04-09T10:00)")

            if start_at.tzinfo is not None:
                start_at = start_at.astimezone().replace(tzinfo=None)

        title_escaped = _escape(title)

        script_lines = [
            'tell application "Calendar"',
            "    set targetCalendar to first calendar",
        ]
        if start_at is not None:
            script_lines.extend(
                [
                    "    set startDate to current date",
                    f"    set year of startDate to {start_at.year}",
                    f"    set month of startDate to {start_at.month}",
                    f"    set day of startDate to {start_at.day}",
                    f"    set hours of startDate to {start_at.hour}",
                    f"    set minutes of startDate to {start_at.minute}",
                    f"    set seconds of startDate to {start_at.second}",
                ]
            )
        else:
            script_lines.append(f"    set startDate to (current date) + ({start_offset_minutes} * minutes)")

        script_lines.extend(
            [
                f"    set endDate to startDate + ({duration_minutes} * minutes)",
                "    tell targetCalendar",
                f'        make new event with properties {{summary:"{title_escaped}", start date:startDate, end date:endDate}}',
                "    end tell",
                "end tell",
            ]
        )
        script = "\n".join(script_lines)

        process = await run_command(["osascript", "-e", script])
        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "AppleScript Fehler")

        if start_at is not None:
            label = start_at.strftime("%Y-%m-%d %H:%M")
            return ToolResult(success=True, output=f"Kalendereintrag erstellt: {title} (Start {label}, Dauer {duration_minutes} min)")

        return ToolResult(success=True, output=f"Kalendereintrag erstellt: {title}")
