import pytest
from pydantic import ValidationError

from jarvis_agent.domain import Observation, PolicyDecision, PolicyVerdict


@pytest.mark.parametrize("verdict", list(PolicyVerdict))
def test_all_verdicts_are_explicit_records(policy_payload, verdict):
    decision = PolicyDecision(**{**policy_payload, "verdict": verdict})
    assert decision.verdict is verdict
    assert decision.policy_source == "test-fixture"


@pytest.mark.parametrize("field", ["reason_code", "human_reason", "policy_source"])
@pytest.mark.parametrize("value", ["", " \t\n", None, 3])
def test_policy_requires_nonblank_explanation_and_provenance(policy_payload, field, value):
    with pytest.raises(ValidationError):
        PolicyDecision(**{**policy_payload, field: value})


@pytest.mark.parametrize("verdict", ["ALLOW", "trusted", "block", None, True])
def test_rejects_unknown_policy_verdicts(policy_payload, verdict):
    with pytest.raises(ValidationError):
        PolicyDecision(**{**policy_payload, "verdict": verdict})


def test_successful_observation_and_failure_with_optional_detail(observation_payload):
    success = Observation(**observation_payload)
    assert success.duration_ms == 0
    assert success.error_code is None
    failure = Observation(**{**observation_payload, "success": False, "error_code": "ACTION_TIMEOUT"})
    assert failure.error_detail is None
    detailed = Observation(**{**failure.model_dump(), "error_detail": "Timed out in the test adapter."})
    assert detailed.success is False


@pytest.mark.parametrize("field", ["error_code", "error_detail"])
def test_success_cannot_report_an_error(observation_payload, field):
    with pytest.raises(ValidationError, match="successful observation"):
        Observation(**{**observation_payload, field: "unexpected error"})


def test_failure_requires_stable_error_code(observation_payload):
    with pytest.raises(ValidationError, match="requires an error_code"):
        Observation(**{**observation_payload, "success": False})


@pytest.mark.parametrize("value", [-1, 0.5, 1.0, "1", True, None])
def test_duration_is_nonnegative_strict_integer(observation_payload, value):
    with pytest.raises(ValidationError):
        Observation(**{**observation_payload, "duration_ms": value})


@pytest.mark.parametrize("value", [0, 1, "true", "false", None])
def test_observation_success_is_strict_boolean(observation_payload, value):
    with pytest.raises(ValidationError):
        Observation(**{**observation_payload, "success": value})


@pytest.mark.parametrize("field", ["summary", "error_code", "error_detail"])
@pytest.mark.parametrize("value", ["", " \n", 3])
def test_observation_text_fields_are_nonblank_when_present(observation_payload, field, value):
    payload = {**observation_payload, "success": False, "error_code": "ACTION_FAILED", field: value}
    with pytest.raises(ValidationError):
        Observation(**payload)


@pytest.mark.parametrize("value", ["2026-10-06T17:00:00", "not-a-date", 1791306000])
def test_observation_requires_aware_timestamp(observation_payload, value):
    with pytest.raises(ValidationError):
        Observation(**{**observation_payload, "occurred_at": value})


@pytest.mark.parametrize("data", [[], None, {"value": float("nan")}, {"value": object()}, {"nested": {1: "x"}}])
def test_observation_data_uses_same_json_boundary(observation_payload, data):
    with pytest.raises(ValidationError):
        Observation(**{**observation_payload, "data": data})
