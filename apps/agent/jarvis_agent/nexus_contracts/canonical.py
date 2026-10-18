"""JCS bytes only: no file access, transport, secrets or runtime reconciliation."""

import json
import math

import rfc8785

from .constants import MAX_SAFE_INTEGER


def _prepare(value: object, ancestors: set[int], depth: int) -> object:
    if depth > 64:
        raise ValueError("JSON depth exceeds 64")
    if value is None or type(value) is bool:
        return value
    if type(value) is str:
        value.encode("utf-8")  # Reject lone surrogate code points, including keys.
        return value
    if type(value) is int:
        if abs(value) <= MAX_SAFE_INTEGER:
            return value
        number = float(value)
        if not math.isfinite(number) or int(number) != value:
            raise ValueError("Integer is not exactly representable as binary64")
        return number
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Non-finite JSON number")
        return value
    if type(value) not in (dict, list) or id(value) in ancestors:
        raise ValueError("Expected an acyclic plain JSON value")
    ancestors.add(id(value))
    try:
        if type(value) is list:
            return [_prepare(item, ancestors, depth + 1) for item in value]
        if any(type(key) is not str for key in value):
            raise ValueError("JSON object keys must be strings")
        return {
            _prepare(key, set(), 0): _prepare(item, ancestors, depth + 1)
            for key, item in value.items()
        }
    finally:
        ancestors.remove(id(value))


def canonical_bytes(value: object) -> bytes:
    """RFC 8785 UTF-8, without BOM/final LF; Unicode/newlines stay unchanged."""
    return rfc8785.dumps(_prepare(value, set(), 0))


def canonical_json(value: object) -> str:
    return canonical_bytes(value).decode("utf-8")


def _parse_integer(text: str) -> int | float:
    integer = int(text)
    # JSON.parse uses binary64, also for lexically integral numbers outside the
    # safe-integer range. The schema separately bounds integer-valued fields.
    return integer if abs(integer) <= MAX_SAFE_INTEGER else float(text)


def _reject_constant(text: str) -> None:
    raise ValueError(f"Non-JSON number: {text}")


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def parse_json(source: str | bytes) -> object:
    """Decode JSON with ECMAScript binary64 numbers, without accepting NaN."""
    return json.loads(
        source, parse_int=_parse_integer, parse_constant=_reject_constant,
        object_pairs_hook=_object,
    )


def parse_canonical_file(source: bytes) -> object:
    """Verify canonical UTF-8 plus exactly one LF; never repair corpus bytes."""
    if source.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 BOM is forbidden")
    value = parse_json(source.decode("utf-8", errors="strict"))
    if source != canonical_bytes(value) + b"\n":
        raise ValueError("Non-canonical corpus bytes")
    return value
