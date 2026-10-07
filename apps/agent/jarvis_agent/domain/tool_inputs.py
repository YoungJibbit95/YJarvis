"""Inert semantic input contracts; no legacy conversion or provider resolution."""

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, AnyHttpUrl, BeforeValidator, Field, StrictBool, StrictInt, StrictStr

from .common import DomainModel, NonBlankText


def _app_name(value: str) -> str:
    # A deliberately bounded display-name grammar, not an installed-app lookup
    # or a security boundary. Providers must never interpret this as a command.
    if (not re.fullmatch(r"[^\W_][\w .()+-]{0,199}", value)
            or value != value.strip()
            or re.search(r"(?:^|\s)--?\S|(?:[\w-]+\.){2,}[\w-]+", value)
            or value.lower().endswith((".app", ".exe", ".com", ".bat", ".cmd", ".ps1", ".scpt"))):
        raise ValueError("app_name must be a display name, not a path, bundle ID or command")
    return value


def _calendar_datetime(value: object) -> datetime:
    # Preserve naive/aware values; do not consult the host clock or timezone.
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and ("T" in value or " " in value):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError("expected an ISO datetime with a time, or a datetime object")


CalendarDateTime = Annotated[datetime, Field(strict=True), BeforeValidator(_calendar_datetime)]
RaycastSegment = Annotated[StrictStr, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,120}$")]
FolderName = Annotated[NonBlankText, Field(max_length=120)]
Recipient = Annotated[NonBlankText, Field(max_length=220)]
ListLimit = Annotated[StrictInt, Field(ge=1, le=30)]


class UrlOpenInput(DomainModel):
    url: Annotated[AnyHttpUrl, Field(strict=True)]


class AppOpenInput(DomainModel):
    app_name: Annotated[NonBlankText, Field(max_length=200), AfterValidator(_app_name)]


class RaycastOpenInput(DomainModel):
    fallback_text: StrictStr | None = None


class RaycastCommandRunInput(DomainModel):
    owner: RaycastSegment
    extension: RaycastSegment
    command: RaycastSegment
    fallback_text: StrictStr | None = None
    background: StrictBool = True


class ClipboardReadInput(DomainModel):
    """No arguments; DomainModel forbids even incidental extra fields."""


class ClipboardWriteInput(DomainModel):
    text: StrictStr


class ReminderCreateInput(DomainModel):
    title: NonBlankText
    notes: StrictStr | None = None
    due_at: CalendarDateTime | None = None


class ReminderListInput(DomainModel):
    limit: ListLimit = 8
    list_name: FolderName | None = None


class CalendarCreateEventInput(DomainModel):
    title: NonBlankText
    start_at: CalendarDateTime | None = None
    # Absolute start_at takes precedence, as in legacy. No start is computed here.
    start_offset_minutes: StrictInt = 5
    duration_minutes: Annotated[StrictInt, Field(ge=1, le=1440)] = 60


class CalendarListEventsInput(DomainModel):
    days_ahead: Annotated[StrictInt, Field(ge=1, le=90)] = 7
    limit: Annotated[StrictInt, Field(ge=1, le=40)] = 10


class NotesCreateInput(DomainModel):
    title: Annotated[NonBlankText, Field(max_length=180)]
    content: Annotated[StrictStr, Field(max_length=8000)]
    folder: FolderName | None = None


class NotesSearchInput(DomainModel):
    query: Annotated[StrictStr, Field(max_length=200)] = ""
    folder: FolderName | None = None
    limit: ListLimit = 8


class MailCreateDraftInput(DomainModel):
    subject: Annotated[NonBlankText, Field(max_length=220)]
    content: Annotated[StrictStr, Field(max_length=12000)]
    recipient: Recipient | None = None


class MessagesSendInput(DomainModel):
    recipient: Recipient
    text: Annotated[NonBlankText, Field(max_length=4000)]


class ContactsSearchInput(DomainModel):
    query: Annotated[StrictStr, Field(max_length=180)] = ""
    limit: ListLimit = 6


class MusicControlInput(DomainModel):
    action: Literal["play", "pause", "next", "previous"]


class FileReadInput(DomainModel):
    path: NonBlankText


class FileWriteInput(DomainModel):
    path: NonBlankText
    content: StrictStr
    mode: Literal["overwrite", "append"] = "overwrite"
