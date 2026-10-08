"""Successful capability data only; outcome and execution belong to Observation.

These inert contracts do not parse legacy prose or assert that execution occurred.
"""

from typing import Annotated

from pydantic import BeforeValidator, StrictStr

from .common import DomainModel, ordered_sequence


TextSequence = Annotated[tuple[StrictStr, ...], BeforeValidator(ordered_sequence)]


class NoDataOutput(DomainModel):
    """No stable result data for a side effect; not a success/approval flag."""


class ClipboardReadOutput(DomainModel):
    text: StrictStr


class FileReadOutput(DomainModel):
    """Full decoded text, without synthetic preview/truncation markers."""

    content: StrictStr


class ReminderListOutput(DomainModel):
    """Titles of returned reminders, not identities or a complete inventory."""

    titles: TextSequence


class CalendarListEventsOutput(DomainModel):
    """Titles of returned events; no date/time interpretation or event identity."""

    titles: TextSequence


class NotesSearchOutput(DomainModel):
    """Titles of returned notes; no IDs, bodies or folder/provider metadata."""

    titles: TextSequence


class ContactsSearchOutput(DomainModel):
    """Display names of returned contacts, not addresses or recipient identifiers."""

    names: TextSequence
