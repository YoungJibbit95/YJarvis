from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from jarvis_agent.domain import InputMode, Turn, TurnState


@pytest.mark.parametrize("state", list(TurnState))
@pytest.mark.parametrize("input_mode", list(InputMode))
def test_turn_supports_architecture_states_without_running_transitions(turn_payload, state, input_mode):
    turn = Turn(**{**turn_payload, "state": state, "input_mode": input_mode})
    assert turn.state is state
    assert turn.input_mode is input_mode
    assert turn.id == UUID(int=10)
    assert turn.user_text == turn_payload["user_text"]
    assert turn.created_at == turn.updated_at  # Same instant, different offsets.


def test_default_turn_state_and_explicit_datetime_inputs(turn_payload):
    turn_payload["created_at"] = datetime(2026, 10, 6, 17, tzinfo=timezone.utc)
    turn = Turn(**turn_payload)
    assert turn.state is TurnState.RECEIVED
    assert turn.created_at == turn_payload["created_at"]


@pytest.mark.parametrize("field", ["created_at", "updated_at"])
@pytest.mark.parametrize("value", ["2026-10-06T17:00:00", "2026-10-06", "invalid", 1791306000, "1791306000", None, datetime(2026, 10, 6)])
def test_rejects_naive_or_ambiguous_timestamps(turn_payload, field, value):
    with pytest.raises(ValidationError):
        Turn(**{**turn_payload, field: value})


def test_rejects_reversed_timestamp_order(turn_payload):
    with pytest.raises(ValidationError, match="updated_at must not precede"):
        Turn(**{**turn_payload, "updated_at": "2026-10-06T16:59:59Z"})


@pytest.mark.parametrize("value", ["", " \t\n", 3, b"text"])
def test_user_text_must_be_nonblank_string(turn_payload, value):
    with pytest.raises(ValidationError):
        Turn(**{**turn_payload, "user_text": value})


@pytest.mark.parametrize("field,value", [("state", "thinking"), ("input_mode", "audio"), ("state", "COMPLETED"), ("input_mode", None)])
def test_legacy_or_unknown_enum_values_do_not_silently_map(turn_payload, field, value):
    with pytest.raises(ValidationError):
        Turn(**{**turn_payload, field: value})


def test_timestamp_order_compares_instants_across_dst_fold(turn_payload):
    from zoneinfo import ZoneInfo

    berlin = ZoneInfo("Europe/Berlin")
    turn_payload.update(
        created_at=datetime(2020, 10, 25, 2, 30, tzinfo=berlin, fold=0),
        updated_at=datetime(2020, 10, 25, 2, 15, tzinfo=berlin, fold=1),
    )
    assert Turn(**turn_payload).created_at.hour == 2
    turn_payload["created_at"], turn_payload["updated_at"] = (
        turn_payload["updated_at"], turn_payload["created_at"]
    )
    with pytest.raises(ValidationError, match="updated_at must not precede"):
        Turn(**turn_payload)
