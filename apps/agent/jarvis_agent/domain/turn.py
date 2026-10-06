"""Turn snapshots, without orchestration or a transition engine."""

from __future__ import annotations

from datetime import timezone
from enum import StrEnum
from typing import Self

from pydantic import model_validator

from .common import DomainId, DomainModel, NonBlankText, Timestamp


class InputMode(StrEnum):
    TEXT = "text"
    VOICE = "voice"


class TurnState(StrEnum):
    RECEIVED = "received"
    CONTEXT_BUILDING = "context_building"
    ROUTING = "routing"
    PLANNING = "planning"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    RESPONDING = "responding"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Turn(DomainModel):
    """IDs and timezone-aware timestamps come from the caller, not the clock."""

    id: DomainId
    session_id: DomainId
    input_mode: InputMode
    user_text: NonBlankText
    state: TurnState = TurnState.RECEIVED
    created_at: Timestamp
    updated_at: Timestamp

    @model_validator(mode="after")
    def validate_timestamps(self) -> Self:
        # Compare instants, including two folds of the same DST timezone.
        if self.updated_at.astimezone(timezone.utc) < self.created_at.astimezone(timezone.utc):
            raise ValueError("updated_at must not precede created_at")
        return self
