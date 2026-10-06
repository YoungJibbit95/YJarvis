from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from jarvis_agent.domain import Action, ActionMode, RiskLevel


@pytest.mark.parametrize("mode", list(ActionMode))
@pytest.mark.parametrize("risk", list(RiskLevel))
def test_explicit_metadata_is_data_not_a_policy_matrix(action_payload, mode, risk):
    action = Action(**{**action_payload, "mode": mode, "risk": risk})
    assert action.mode is mode
    assert action.risk is risk
    assert action.id == UUID(int=1)
    assert action.capability == "example.first"  # No registry lookup.


@pytest.mark.parametrize(
    "capability",
    ["", "open", "Apps.open", "apps..open", ".open", "apps.", "apps.open ", "apps.open\n", "apps.open-now", 1, b"apps.open"],
)
def test_rejects_malformed_capability_names(action_payload, capability):
    with pytest.raises(ValidationError):
        Action(**{**action_payload, "capability": capability})


@pytest.mark.parametrize("field", ["reversible", "requires_result"])
@pytest.mark.parametrize("value", ["true", "false", 0, 1, None])
def test_booleans_are_not_coerced(action_payload, field, value):
    with pytest.raises(ValidationError):
        Action(**{**action_payload, field: value})


@pytest.mark.parametrize("field,value", [("mode", "execute"), ("risk", "safe"), ("mode", None), ("risk", 0)])
def test_rejects_unknown_metadata(action_payload, field, value):
    with pytest.raises(ValidationError):
        Action(**{**action_payload, field: value})


def test_nested_json_preserves_types_and_text_and_copies_inputs(action_payload):
    arguments = {"all": [None, True, False, 7, 1.5, "  unchanged  ", {"nested": ["value"]}]}
    action = Action(**{**action_payload, "arguments": arguments})
    assert action.arguments == arguments
    assert type(action.arguments["all"][1]) is bool
    assert type(action.arguments["all"][3]) is int
    arguments["all"][6]["nested"].append("later edit")
    assert action.arguments["all"][6]["nested"] == ["value"]


@pytest.mark.parametrize("arguments", [None, [], "{}", [("a", 1)], {1: "value"}, {b"a": 1}, {"nested": {1: "value"}}])
def test_arguments_must_be_json_objects_with_string_keys(action_payload, arguments):
    with pytest.raises(ValidationError):
        Action(**{**action_payload, "arguments": arguments})


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf"), b"bytes", {1, 2}, (1, 2), UUID(int=1), datetime(2026, 10, 6, tzinfo=timezone.utc), Decimal("1.2"), object()],
)
def test_rejects_non_json_values_even_when_nested(action_payload, value):
    with pytest.raises(ValidationError):
        Action(**{**action_payload, "arguments": {"nested": [{"value": value}]}})


@pytest.mark.parametrize("container_kind", ["dict", "list"])
def test_rejects_cyclic_json_without_recursion_errors(action_payload, container_kind):
    cyclic = {} if container_kind == "dict" else []
    if container_kind == "dict":
        cyclic["self"] = cyclic
    else:
        cyclic.append(cyclic)
    with pytest.raises(ValidationError, match="cyclic references"):
        Action(**{**action_payload, "arguments": {"value": cyclic}})


def test_repeated_noncyclic_json_aliases_are_valid(action_payload):
    shared = {"values": [1, 2]}
    action = Action(**{**action_payload, "arguments": {"left": shared, "right": shared}})
    assert action.arguments == {"left": {"values": [1, 2]}, "right": {"values": [1, 2]}}


def test_callback_payload_is_rejected_without_calling_it(action_payload):
    calls = []

    def callback():
        calls.append("executed")

    with pytest.raises(ValidationError):
        Action(**{**action_payload, "arguments": {"callback": callback}})
    assert calls == []
