"""Shared validation primitives; no application services or environment access."""

from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    StrictStr,
)


class DomainModel(BaseModel):
    """Validated records, not authority to execute an action.

    Attribute assignment is disabled. JSON dictionaries/lists are not deeply
    frozen: validate again at boundaries after editing payloads. Pydantic's
    model_construct/model_copy(update=...) are not validation entry points.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        revalidate_instances="always",
        allow_inf_nan=False,
    )


def _parse_id(value: object) -> UUID:
    if isinstance(value, UUID):
        identifier = value
    elif isinstance(value, str):
        try:
            identifier = UUID(value)
        except ValueError as exc:
            raise ValueError("ID must be a UUID or UUID string") from exc
    else:
        raise ValueError("ID must be a UUID or UUID string")
    if identifier.int == 0:
        raise ValueError("ID must not be the nil UUID")
    return identifier


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("text must contain a non-whitespace character")
    # Validate, but do not silently alter the user's text or argument values.
    return value


def _parse_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("timestamp must be an ISO 8601 datetime") from exc
    raise ValueError("timestamp must be a datetime or ISO 8601 string, not an epoch")


def ordered_sequence(value: object) -> object:
    """Accept ordered Python/JSON arrays, never sets or lazy iterators."""
    if not isinstance(value, (list, tuple)):
        raise ValueError("expected an ordered list or tuple")
    return value


def _json_object(value: object) -> object:
    """Reject coercible non-JSON objects, non-string keys, NaN/Inf and cycles.

    This iterative precheck never calls payload objects. Pydantic then validates
    and copies the typed JSON tree. Repeated, non-cyclic container aliases are OK.
    """
    if type(value) is not dict:
        raise ValueError("expected a JSON object with string keys")
    active: set[int] = set()
    pending: list[tuple[object, bool]] = [(value, False)]
    while pending:
        item, leaving = pending.pop()
        if leaving:
            active.remove(id(item))
            continue
        kind = type(item)
        if kind in (dict, list):
            if id(item) in active:
                raise ValueError("JSON data must not contain cyclic references")
            if kind is dict and any(type(key) is not str for key in item):
                raise ValueError("JSON object keys must be strings")
            active.add(id(item))
            pending.append((item, True))
            values = item.values() if kind is dict else item
            pending.extend((child, False) for child in values)
        elif kind is float:
            if not isfinite(item):
                raise ValueError("JSON numbers must be finite")
        elif item is not None and kind not in (str, int, bool):
            raise ValueError("data must contain only JSON values")
    return value


DomainId = Annotated[UUID, BeforeValidator(_parse_id)]
NonBlankText = Annotated[StrictStr, Field(min_length=1), AfterValidator(_nonblank)]
Timestamp = Annotated[AwareDatetime, BeforeValidator(_parse_timestamp)]
JsonObject = Annotated[dict[str, JsonValue], BeforeValidator(_json_object)]
