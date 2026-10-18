"""Wire scalar constraints; preserve strings instead of parsing them to dates."""

import math
import re
from datetime import date
from typing import Annotated, Literal, TypeVar

from pydantic import AfterValidator, BeforeValidator, Field

from .canonical import canonical_bytes
from .constants import MAX_SAFE_INTEGER


def scalar_text(value: str) -> str:
    value.encode("utf-8")
    return value


def _id(value: str) -> str:
    if re.search(r"[\u0000-\u0020\u007f]", value):
        raise ValueError("Invalid wire ID")
    return scalar_text(value)


def _title(value: str) -> str:
    if not re.search(
        r"[^\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a"
        r"\u2028\u2029\u202f\u205f\u3000\ufeff]", value,
    ):
        raise ValueError("Blank title")
    return scalar_text(value)


def _date(value: str) -> str:
    if not re.fullmatch(r"(?!0000)[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Invalid date profile")
    date.fromisoformat(value)
    return value


def _instant(value: str) -> str:
    if not re.fullmatch(
        r"(?!0000)[0-9]{4}-[0-9]{2}-[0-9]{2}T([01][0-9]|2[0-3]):"
        r"[0-5][0-9]:[0-5][0-9](\.[0-9]{1,9})?"
        r"(Z|\+([01][0-9]|2[0-3]):[0-5][0-9]|-(?!00:00$)"
        r"([01][0-9]|2[0-3]):[0-5][0-9])", value,
    ):
        raise ValueError("Invalid instant profile")
    _date(value[:10])
    return value


def json_integer(value: object) -> int:
    if type(value) is int:
        return value
    if type(value) is float and math.isfinite(value) and value.is_integer():
        return int(value)
    raise ValueError("Expected a JSON integer, not a boolean/string")


def json_boolean(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError("Expected a JSON boolean")
    return value


def unique(values: list) -> list:
    encodings = [canonical_bytes(item.to_wire() if hasattr(item, "to_wire") else item) for item in values]
    if len(encodings) != len(set(encodings)):
        raise ValueError("Expected unique JSON array items")
    return values


Id = Annotated[str, Field(strict=True, min_length=1, max_length=200), AfterValidator(_id)]
Digest = Annotated[str, Field(strict=True, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")]
Title = Annotated[str, Field(strict=True, min_length=1, max_length=512), AfterValidator(_title)]
Instant = Annotated[str, Field(strict=True, max_length=40), AfterValidator(_instant)]
Date = Annotated[str, Field(strict=True, max_length=10), AfterValidator(_date)]
TimeZone = Annotated[
    str, Field(strict=True, min_length=1, max_length=100),
    AfterValidator(lambda v: v if re.fullmatch(r"(UTC|[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+.-]+)+)", v)
                   else _bad("Invalid timezone syntax")),
]
CursorText = Annotated[
    str, Field(strict=True, min_length=16, max_length=2048),
    AfterValidator(lambda v: v if re.fullmatch(r"[A-Za-z0-9_-]+", v) else _bad("Invalid opaque cursor")),
]
SchemaVersionText = Annotated[
    str, Field(strict=True, max_length=32),
    AfterValidator(lambda v: v if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", v) else _bad("Invalid schema version")),
]
SafeInteger = Annotated[int, BeforeValidator(json_integer), Field(strict=True, ge=0, le=MAX_SAFE_INTEGER)]
PageLimit = Annotated[SafeInteger, Field(ge=1, le=100)]
BoundedLength = Annotated[SafeInteger, Field(le=65_536)]
FiniteNumber = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=-MAX_SAFE_INTEGER, le=MAX_SAFE_INTEGER)]
Duration = Annotated[FiniteNumber, Field(ge=0.01, le=10_080)]
Text = Annotated[str, Field(strict=True), AfterValidator(scalar_text)]
Tag = Annotated[Text, Field(min_length=1, max_length=64)]
T = TypeVar("T")
UniqueList = Annotated[list[T], AfterValidator(unique)]
Tags = Annotated[UniqueList[Tag], Field(max_length=32)]
TrueValue = Annotated[Literal[True], BeforeValidator(json_boolean)]
FalseValue = Annotated[Literal[False], BeforeValidator(json_boolean)]


def _bad(message: str):
    raise ValueError(message)
