from __future__ import annotations

from datetime import datetime
from typing import Any

from .base import BaseTool, ToolContext, ToolResult, ToolSpec, run_command


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _clean_text(value: str, *, fallback: str = "", max_len: int = 4000) -> str:
    cleaned = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if not cleaned:
        cleaned = fallback
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    return cleaned


def _bounded_int(raw: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


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


class NotesCreateTool(BaseTool):
    spec = ToolSpec(
        tool_name="notes_create",
        risk_level="medium",
        requires_approval=True,
        input_schema={
            "title": "string",
            "content": "string",
            "folder": "string",
        },
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        title = _clean_text(tool_input.get("title", ""), fallback="Neue Notiz", max_len=180)
        content = _clean_text(tool_input.get("content", ""), fallback=title, max_len=8000)
        folder = _clean_text(tool_input.get("folder", ""), fallback="", max_len=120)

        script_lines = [
            'tell application "Notes"',
            f'    set folderName to "{_escape(folder)}"',
            f'    set noteTitle to "{_escape(title)}"',
            f'    set noteBody to "{_escape(content)}"',
            "    set targetAccount to default account",
            "    if folderName is \"\" then",
            "        set targetFolder to default folder of targetAccount",
            "    else",
            "        if exists folder folderName of targetAccount then",
            "            set targetFolder to folder folderName of targetAccount",
            "        else",
            "            set targetFolder to make new folder at targetAccount with properties {name:folderName}",
            "        end if",
            "    end if",
            "    make new note at targetFolder with properties {name:noteTitle, body:noteBody}",
            "end tell",
        ]
        script = "\n".join(script_lines)

        process = await run_command(["osascript", "-e", script])
        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "Notiz konnte nicht erstellt werden")

        if folder:
            return ToolResult(success=True, output=f"Notiz erstellt: {title} (Ordner: {folder})")
        return ToolResult(success=True, output=f"Notiz erstellt: {title}")


class NotesSearchTool(BaseTool):
    spec = ToolSpec(
        tool_name="notes_search",
        risk_level="low",
        requires_approval=True,
        input_schema={
            "query": "string",
            "limit": "number",
            "folder": "string",
        },
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        query = _clean_text(tool_input.get("query", ""), fallback="", max_len=200)
        folder = _clean_text(tool_input.get("folder", ""), fallback="", max_len=120)
        limit = _bounded_int(tool_input.get("limit"), default=8, minimum=1, maximum=30)

        script_lines = [
            'tell application "Notes"',
            f'    set queryText to "{_escape(query)}"',
            f'    set folderName to "{_escape(folder)}"',
            f"    set maxCount to {limit}",
            "    set outLines to {}",
            "    set notePool to {}",
            "    set targetAccount to default account",
            "    if folderName is \"\" then",
            "        set notePool to every note of targetAccount",
            "    else",
            "        if exists folder folderName of targetAccount then",
            "            set notePool to every note of folder folderName of targetAccount",
            "        else",
            "            return \"__FOLDER_NOT_FOUND__\"",
            "        end if",
            "    end if",
            "    repeat with n in notePool",
            "        set nName to (name of n as text)",
            "        set nBody to (body of n as text)",
            "        if queryText is \"\" then",
            "            set end of outLines to nName",
            "        else",
            "            ignoring case",
            "                if nName contains queryText or nBody contains queryText then",
            "                    set end of outLines to nName",
            "                end if",
            "            end ignoring",
            "        end if",
            "        if (count of outLines) >= maxCount then exit repeat",
            "    end repeat",
            "    set AppleScript's text item delimiters to linefeed",
            "    set joinedOutput to outLines as text",
            "    set AppleScript's text item delimiters to \"\"",
            "    return joinedOutput",
            "end tell",
        ]
        script = "\n".join(script_lines)
        process = await run_command(["osascript", "-e", script])
        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "Notizen konnten nicht gelesen werden")

        output = (process.stdout or "").strip()
        if output == "__FOLDER_NOT_FOUND__":
            return ToolResult(success=False, output="", error=f"Notiz-Ordner nicht gefunden: {folder}")

        if not output:
            if query:
                return ToolResult(success=True, output=f"Keine Notizen zu `{query}` gefunden.")
            return ToolResult(success=True, output="Keine Notizen gefunden.")

        lines = [line.strip() for line in output.splitlines() if line.strip()]
        preview = "\n".join(f"- {line}" for line in lines[:limit])
        if query:
            return ToolResult(success=True, output=f"Notiztreffer fuer `{query}`:\n{preview}")
        return ToolResult(success=True, output=f"Notizen ({len(lines)}):\n{preview}")


class ReminderListTool(BaseTool):
    spec = ToolSpec(
        tool_name="reminder_list",
        risk_level="low",
        requires_approval=True,
        input_schema={
            "limit": "number",
            "list_name": "string",
        },
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        limit = _bounded_int(tool_input.get("limit"), default=8, minimum=1, maximum=30)
        list_name = _clean_text(tool_input.get("list_name", ""), fallback="", max_len=120)

        script_lines = [
            'tell application "Reminders"',
            f"    set maxCount to {limit}",
            f'    set listName to "{_escape(list_name)}"',
            "    set reminderPool to {}",
            "    if listName is \"\" then",
            "        set reminderPool to reminders of default list",
            "    else",
            "        if exists list listName then",
            "            set reminderPool to reminders of list listName",
            "        else",
            "            return \"__LIST_NOT_FOUND__\"",
            "        end if",
            "    end if",
            "    set outLines to {}",
            "    repeat with r in reminderPool",
            "        if completed of r is false then",
            "            set rName to name of r as text",
            "            set dueValue to due date of r",
            "            if dueValue is missing value then",
            "                set end of outLines to rName",
            "            else",
            "                set end of outLines to rName & \" | \" & (dueValue as text)",
            "            end if",
            "        end if",
            "        if (count of outLines) >= maxCount then exit repeat",
            "    end repeat",
            "    set AppleScript's text item delimiters to linefeed",
            "    set joinedOutput to outLines as text",
            "    set AppleScript's text item delimiters to \"\"",
            "    return joinedOutput",
            "end tell",
        ]
        script = "\n".join(script_lines)
        process = await run_command(["osascript", "-e", script])
        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "Erinnerungen konnten nicht gelesen werden")

        output = (process.stdout or "").strip()
        if output == "__LIST_NOT_FOUND__":
            return ToolResult(success=False, output="", error=f"Erinnerungsliste nicht gefunden: {list_name}")
        if not output:
            return ToolResult(success=True, output="Keine offenen Erinnerungen gefunden.")
        return ToolResult(success=True, output=f"Offene Erinnerungen:\n{output}")


class CalendarListEventsTool(BaseTool):
    spec = ToolSpec(
        tool_name="calendar_list_events",
        risk_level="low",
        requires_approval=True,
        input_schema={
            "days_ahead": "number",
            "limit": "number",
        },
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        days_ahead = _bounded_int(tool_input.get("days_ahead"), default=7, minimum=1, maximum=90)
        limit = _bounded_int(tool_input.get("limit"), default=10, minimum=1, maximum=40)

        script_lines = [
            'tell application "Calendar"',
            f"    set dayWindow to {days_ahead}",
            f"    set maxCount to {limit}",
            "    set startDate to current date",
            "    set endDate to (current date) + (dayWindow * days)",
            "    set outLines to {}",
            "    set eventPool to every event of first calendar whose start date >= startDate and start date <= endDate",
            "    repeat with ev in eventPool",
            "        set evTitle to summary of ev as text",
            "        set evStart to start date of ev",
            "        set end of outLines to evTitle & \" | \" & (evStart as text)",
            "        if (count of outLines) >= maxCount then exit repeat",
            "    end repeat",
            "    set AppleScript's text item delimiters to linefeed",
            "    set joinedOutput to outLines as text",
            "    set AppleScript's text item delimiters to \"\"",
            "    return joinedOutput",
            "end tell",
        ]
        script = "\n".join(script_lines)
        process = await run_command(["osascript", "-e", script])
        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "Kalenderevents konnten nicht gelesen werden")

        output = (process.stdout or "").strip()
        if not output:
            return ToolResult(success=True, output=f"Keine Termine in den naechsten {days_ahead} Tagen gefunden.")
        return ToolResult(success=True, output=f"Kommende Termine ({days_ahead} Tage):\n{output}")


class MailCreateDraftTool(BaseTool):
    spec = ToolSpec(
        tool_name="mail_create_draft",
        risk_level="medium",
        requires_approval=True,
        input_schema={
            "subject": "string",
            "content": "string",
            "to": "string",
        },
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        subject = _clean_text(tool_input.get("subject", ""), fallback="Neue Nachricht", max_len=220)
        content = _clean_text(tool_input.get("content", ""), fallback="Hallo,", max_len=12000)
        recipient = _clean_text(tool_input.get("to", ""), fallback="", max_len=220)

        script_lines = [
            'tell application "Mail"',
            f'    set mailSubject to "{_escape(subject)}"',
            f'    set mailBody to "{_escape(content)}"',
            f'    set recipientAddress to "{_escape(recipient)}"',
            "    set outgoingMessage to make new outgoing message with properties {subject:mailSubject, content:mailBody, visible:false}",
            "    if recipientAddress is not \"\" then",
            "        tell outgoingMessage",
            "            make new to recipient at end of to recipients with properties {address:recipientAddress}",
            "        end tell",
            "    end if",
            "end tell",
        ]
        script = "\n".join(script_lines)
        process = await run_command(["osascript", "-e", script])
        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "Mail-Entwurf konnte nicht erstellt werden")

        if recipient:
            return ToolResult(success=True, output=f"Mail-Entwurf erstellt: {subject} -> {recipient}")
        return ToolResult(success=True, output=f"Mail-Entwurf erstellt: {subject}")


class MessagesSendTool(BaseTool):
    spec = ToolSpec(
        tool_name="messages_send",
        risk_level="high",
        requires_approval=True,
        input_schema={
            "to": "string",
            "text": "string",
        },
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        recipient = _clean_text(tool_input.get("to", ""), fallback="", max_len=220)
        text = _clean_text(tool_input.get("text", ""), fallback="", max_len=4000)

        if not recipient:
            return ToolResult(success=False, output="", error="Empfaenger fehlt (`to`).")
        if not text:
            return ToolResult(success=False, output="", error="Nachrichtentext fehlt (`text`).")

        script_lines = [
            'tell application "Messages"',
            f'    set targetHandle to "{_escape(recipient)}"',
            f'    set messageBody to "{_escape(text)}"',
            "    set targetService to first service whose service type = iMessage",
            "    set targetBuddy to buddy targetHandle of targetService",
            "    send messageBody to targetBuddy",
            "end tell",
        ]
        script = "\n".join(script_lines)
        process = await run_command(["osascript", "-e", script])
        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "Nachricht konnte nicht gesendet werden")

        return ToolResult(success=True, output=f"Nachricht an {recipient} gesendet.")


class ContactsSearchTool(BaseTool):
    spec = ToolSpec(
        tool_name="contacts_search",
        risk_level="low",
        requires_approval=True,
        input_schema={
            "query": "string",
            "limit": "number",
        },
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        query = _clean_text(tool_input.get("query", ""), fallback="", max_len=180)
        limit = _bounded_int(tool_input.get("limit"), default=6, minimum=1, maximum=30)

        script_lines = [
            'tell application "Contacts"',
            f'    set queryText to "{_escape(query)}"',
            f"    set maxCount to {limit}",
            "    set outLines to {}",
            "    set peoplePool to people",
            "    repeat with p in peoplePool",
            "        set pName to name of p as text",
            "        if queryText is \"\" then",
            "            set end of outLines to pName",
            "        else",
            "            ignoring case",
            "                if pName contains queryText then",
            "                    set end of outLines to pName",
            "                end if",
            "            end ignoring",
            "        end if",
            "        if (count of outLines) >= maxCount then exit repeat",
            "    end repeat",
            "    set AppleScript's text item delimiters to linefeed",
            "    set joinedOutput to outLines as text",
            "    set AppleScript's text item delimiters to \"\"",
            "    return joinedOutput",
            "end tell",
        ]
        script = "\n".join(script_lines)
        process = await run_command(["osascript", "-e", script])
        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "Kontakte konnten nicht gelesen werden")

        output = (process.stdout or "").strip()
        if not output:
            return ToolResult(success=True, output="Keine passenden Kontakte gefunden.")
        if query:
            return ToolResult(success=True, output=f"Kontakt-Treffer fuer `{query}`:\n{output}")
        return ToolResult(success=True, output=f"Kontakte:\n{output}")


class MusicControlTool(BaseTool):
    spec = ToolSpec(
        tool_name="music_control",
        risk_level="low",
        requires_approval=True,
        input_schema={
            "action": "play|pause|next|previous",
        },
    )

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        action = _clean_text(tool_input.get("action", ""), fallback="", max_len=20).lower()
        if action not in {"play", "pause", "next", "previous"}:
            return ToolResult(success=False, output="", error="Ungueltige Musik-Aktion.")

        script_action_map = {
            "play": "play",
            "pause": "pause",
            "next": "next track",
            "previous": "previous track",
        }
        script = "\n".join(
            [
                'tell application "Music"',
                f"    {script_action_map[action]}",
                "end tell",
            ]
        )
        process = await run_command(["osascript", "-e", script])
        if process.returncode != 0:
            return ToolResult(success=False, output="", error=process.stderr.strip() or "Musiksteuerung fehlgeschlagen")

        return ToolResult(success=True, output=f"Musikaktion ausgefuehrt: {action}")
