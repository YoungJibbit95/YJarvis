"""Static legacy-name -> semantic spec inventory; known does not mean available.

No provider imports, discovery, execution, policy or planner integration. Direct
lookup raises KeyError for unknown legacy names instead of guessing a capability.
"""

from types import MappingProxyType
from typing import Mapping

from .action import ActionMode, RiskLevel
from .tool_spec import ToolSpecV2


def _spec(capability: str, description: str, mode: ActionMode, risk: RiskLevel,
          *, idempotent: bool = False) -> ToolSpecV2:
    return ToolSpecV2(
        capability=capability, description=description, input_model=None, output_model=None,
        mode=mode, default_risk=risk, reversible=False, idempotent=idempotent,
        supports_dry_run=False, timeout_seconds=30.0,
    )


# No rollback/dry-run support is promised. The 30 s descriptive budget is not a
# legacy timeout: nothing reads/enforces it in the current runtime. Typed I/O
# population is deliberately a separate step, not a permissive legacy adapter.
LEGACY_TOOL_CATALOG: Mapping[str, ToolSpecV2] = MappingProxyType({
    "open_url": _spec("url.open", "Open an HTTP(S) URL in the user's browser.",
                      ActionMode.EXTERNAL_SIDE_EFFECT, RiskLevel.MEDIUM),
    "open_app": _spec("apps.open", "Open an application by name.",
                      ActionMode.SYSTEM, RiskLevel.MEDIUM),
    "raycast_open": _spec("raycast.open", "Open optional Raycast integration, optionally with search text.",
                          ActionMode.SYSTEM, RiskLevel.LOW),
    "raycast_run_command": _spec("raycast.command.run", "Invoke an optional Raycast extension command with potentially external effects.",
                                 ActionMode.EXTERNAL_SIDE_EFFECT, RiskLevel.HIGH),
    "clipboard_read": _spec("clipboard.read", "Read clipboard text.",
                            ActionMode.READ, RiskLevel.LOW, idempotent=True),
    "clipboard_write": _spec("clipboard.write", "Replace clipboard text.",
                             ActionMode.WRITE, RiskLevel.MEDIUM),
    "reminder_create": _spec("reminders.create", "Create a reminder, optionally with notes and a due date.",
                             ActionMode.WRITE, RiskLevel.MEDIUM),
    "reminder_list": _spec("reminders.list", "List incomplete reminders from a selected list.",
                           ActionMode.READ, RiskLevel.LOW, idempotent=True),
    "calendar_create_event": _spec("calendar.events.create", "Create a calendar event.",
                                   ActionMode.WRITE, RiskLevel.MEDIUM),
    "calendar_list_events": _spec("calendar.events.list", "List upcoming calendar events.",
                                  ActionMode.READ, RiskLevel.LOW, idempotent=True),
    "notes_create": _spec("notes.create", "Create a note and, if needed, its destination folder.",
                          ActionMode.WRITE, RiskLevel.MEDIUM),
    "notes_search": _spec("notes.search", "Find notes by text, optionally within a folder.",
                          ActionMode.READ, RiskLevel.LOW, idempotent=True),
    "mail_create_draft": _spec("mail.drafts.create", "Create an email draft without sending it.",
                               ActionMode.WRITE, RiskLevel.MEDIUM),
    "messages_send": _spec("messages.send", "Send a message to a recipient.",
                           ActionMode.EXTERNAL_SIDE_EFFECT, RiskLevel.HIGH),
    "contacts_search": _spec("contacts.search", "Find contacts by name.",
                             ActionMode.READ, RiskLevel.LOW, idempotent=True),
    "music_control": _spec("music.control", "Control playback, including next and previous track.",
                           ActionMode.SYSTEM, RiskLevel.LOW),
    "file_read": _spec("files.read", "Read text from a permitted file.",
                       ActionMode.READ, RiskLevel.MEDIUM, idempotent=True),
    "file_write": _spec("files.write", "Overwrite or append text to a permitted file.",
                        ActionMode.WRITE, RiskLevel.HIGH),
})
