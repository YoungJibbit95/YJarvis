"""Semantic spec ownership with explicit, read-only legacy compatibility views.

Future ToolRuntime consumes CAPABILITY_CATALOG, never the legacy-name view.
Known does not mean available. No provider imports, discovery or runtime wiring;
direct lookups raise KeyError for unknown names without guessing or conversion.
"""

from types import MappingProxyType
from typing import Mapping

from pydantic import BaseModel

from .action import ActionMode, CapabilityName, RiskLevel
from .tool_inputs import (
    AppOpenInput, CalendarCreateEventInput, CalendarListEventsInput,
    ClipboardReadInput, ClipboardWriteInput, ContactsSearchInput, FileReadInput,
    FileWriteInput, MailCreateDraftInput, MessagesSendInput, MusicControlInput,
    NotesCreateInput, NotesSearchInput, RaycastCommandRunInput, RaycastOpenInput,
    ReminderCreateInput, ReminderListInput, UrlOpenInput,
)
from .tool_spec import ToolSpecV2
from .tool_outputs import (
    CalendarListEventsOutput, ClipboardReadOutput, ContactsSearchOutput,
    FileReadOutput, NoDataOutput, NotesSearchOutput, ReminderListOutput,
)


def _spec(capability: str, description: str, input_model: type[BaseModel], output_model: type[BaseModel],
          mode: ActionMode, risk: RiskLevel,
          *, idempotent: bool = False) -> ToolSpecV2:
    return ToolSpecV2(
        capability=capability, description=description, input_model=input_model, output_model=output_model,
        mode=mode, default_risk=risk, reversible=False, idempotent=idempotent,
        supports_dry_run=False, timeout_seconds=30.0,
    )


# No rollback/dry-run support is promised. The 30 s descriptive budget is not a
# legacy timeout: nothing reads/enforces it in the current runtime. Input/output
# classes are descriptive only; adapters and runtime wiring remain separate work.
CAPABILITY_CATALOG: Mapping[CapabilityName, ToolSpecV2] = MappingProxyType({
    "url.open": _spec("url.open", "Open an HTTP(S) URL in the user's browser.",
                      UrlOpenInput, NoDataOutput, ActionMode.EXTERNAL_SIDE_EFFECT, RiskLevel.MEDIUM),
    "apps.open": _spec("apps.open", "Open an application by name.",
                      AppOpenInput, NoDataOutput, ActionMode.SYSTEM, RiskLevel.MEDIUM),
    "raycast.open": _spec("raycast.open", "Open optional Raycast integration, optionally with search text.",
                          RaycastOpenInput, NoDataOutput, ActionMode.SYSTEM, RiskLevel.LOW),
    "raycast.command.run": _spec("raycast.command.run", "Invoke an optional Raycast extension command with potentially external effects.",
                                 RaycastCommandRunInput, NoDataOutput, ActionMode.EXTERNAL_SIDE_EFFECT, RiskLevel.HIGH),
    "clipboard.read": _spec("clipboard.read", "Read clipboard text.",
                            ClipboardReadInput, ClipboardReadOutput, ActionMode.READ, RiskLevel.LOW, idempotent=True),
    "clipboard.write": _spec("clipboard.write", "Replace clipboard text.",
                             ClipboardWriteInput, NoDataOutput, ActionMode.WRITE, RiskLevel.MEDIUM),
    "reminders.create": _spec("reminders.create", "Create a reminder, optionally with notes and a due date.",
                             ReminderCreateInput, NoDataOutput, ActionMode.WRITE, RiskLevel.MEDIUM),
    "reminders.list": _spec("reminders.list", "List incomplete reminders from a selected list.",
                           ReminderListInput, ReminderListOutput, ActionMode.READ, RiskLevel.LOW, idempotent=True),
    "calendar.events.create": _spec("calendar.events.create", "Create a calendar event.",
                                   CalendarCreateEventInput, NoDataOutput, ActionMode.WRITE, RiskLevel.MEDIUM),
    "calendar.events.list": _spec("calendar.events.list", "List upcoming calendar events.",
                                  CalendarListEventsInput, CalendarListEventsOutput, ActionMode.READ, RiskLevel.LOW, idempotent=True),
    "notes.create": _spec("notes.create", "Create a note and, if needed, its destination folder.",
                          NotesCreateInput, NoDataOutput, ActionMode.WRITE, RiskLevel.MEDIUM),
    "notes.search": _spec("notes.search", "Find notes by text, optionally within a folder.",
                          NotesSearchInput, NotesSearchOutput, ActionMode.READ, RiskLevel.LOW, idempotent=True),
    "mail.drafts.create": _spec("mail.drafts.create", "Create an email draft without sending it.",
                               MailCreateDraftInput, NoDataOutput, ActionMode.WRITE, RiskLevel.MEDIUM),
    "messages.send": _spec("messages.send", "Send a message to a recipient.",
                           MessagesSendInput, NoDataOutput, ActionMode.EXTERNAL_SIDE_EFFECT, RiskLevel.HIGH),
    "contacts.search": _spec("contacts.search", "Find contacts by name.",
                             ContactsSearchInput, ContactsSearchOutput, ActionMode.READ, RiskLevel.LOW, idempotent=True),
    "music.control": _spec("music.control", "Control playback, including next and previous track.",
                           MusicControlInput, NoDataOutput, ActionMode.SYSTEM, RiskLevel.LOW),
    "files.read": _spec("files.read", "Read text from a permitted file.",
                       FileReadInput, FileReadOutput, ActionMode.READ, RiskLevel.MEDIUM, idempotent=True),
    "files.write": _spec("files.write", "Overwrite or append text to a permitted file.",
                        FileWriteInput, NoDataOutput, ActionMode.WRITE, RiskLevel.HIGH),
})


# Explicit migration knowledge, not a naming heuristic or an execution adapter.
# The semantic catalog above neither derives from nor resolves through this map.
LEGACY_TOOL_TO_CAPABILITY: Mapping[str, CapabilityName] = MappingProxyType({
    "open_url": "url.open",
    "open_app": "apps.open",
    "raycast_open": "raycast.open",
    "raycast_run_command": "raycast.command.run",
    "clipboard_read": "clipboard.read",
    "clipboard_write": "clipboard.write",
    "reminder_create": "reminders.create",
    "reminder_list": "reminders.list",
    "calendar_create_event": "calendar.events.create",
    "calendar_list_events": "calendar.events.list",
    "notes_create": "notes.create",
    "notes_search": "notes.search",
    "mail_create_draft": "mail.drafts.create",
    "messages_send": "messages.send",
    "contacts_search": "contacts.search",
    "music_control": "music.control",
    "file_read": "files.read",
    "file_write": "files.write",
})

# Transitional view for existing utilities: the exact same frozen spec objects,
# not a second inventory. Future ToolRuntime must use CAPABILITY_CATALOG directly.
LEGACY_TOOL_CATALOG: Mapping[str, ToolSpecV2] = MappingProxyType({
    legacy_name: CAPABILITY_CATALOG[capability]
    for legacy_name, capability in LEGACY_TOOL_TO_CAPABILITY.items()
})
