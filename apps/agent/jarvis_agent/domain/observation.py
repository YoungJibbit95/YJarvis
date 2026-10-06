"""Normalized result data; no tool calls, persistence, or conversational output."""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import Field, StrictBool, StrictInt, model_validator

from .common import DomainId, DomainModel, JsonObject, NonBlankText, Timestamp


class Observation(DomainModel):
    action_id: DomainId
    success: StrictBool
    summary: NonBlankText
    data: JsonObject
    error_code: NonBlankText | None = None
    error_detail: NonBlankText | None = None
    duration_ms: Annotated[StrictInt, Field(ge=0)]
    occurred_at: Timestamp

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.success and (self.error_code is not None or self.error_detail is not None):
            raise ValueError("a successful observation must not contain error fields")
        if not self.success and self.error_code is None:
            raise ValueError("a failed observation requires an error_code")
        return self
