import pytest
from pydantic import BaseModel, ValidationError, model_validator

from jarvis_agent.domain import ActionMode, RiskLevel, ToolSpecV2


class ExampleOutput(BaseModel):
    count: int


def spec_payload():
    return dict(capability="example.inspect", description="Describe only", input_model=None,
                output_model=None, mode="read", default_risk="low", reversible=False,
                idempotent=True, supports_dry_run=False, timeout_seconds=30.0)


@pytest.mark.parametrize("mode", list(ActionMode))
@pytest.mark.parametrize("risk", list(RiskLevel))
def test_modes_and_risks_are_metadata_not_policy(mode, risk):
    spec = ToolSpecV2(**(spec_payload() | {"mode": mode.value, "default_risk": risk.value}))
    assert spec.mode is mode
    assert spec.default_risk is risk
    assert not any(hasattr(spec, name) for name in ("execute", "authorize", "requires_approval", "available"))


@pytest.mark.parametrize("name", ["apps.open", "calendar.events.create", "raycast.command.run"])
def test_semantic_names_reuse_the_action_contract(name):
    assert ToolSpecV2(**(spec_payload() | {"capability": name})).capability == name


@pytest.mark.parametrize("field,value", [
    ("capability", ""), ("capability", " "), ("capability", "open_app"),
    ("capability", "Apps.open"), ("capability", "apps..open"), ("capability", "apps.open\n"),
    ("description", ""), ("description", " \t"), ("description", 1),
    ("mode", "allow"), ("default_risk", "safe"),
    ("timeout_seconds", 0), ("timeout_seconds", -1), ("timeout_seconds", float("inf")),
    ("timeout_seconds", float("nan")), ("timeout_seconds", "30"), ("timeout_seconds", True),
    ("input_model", {}), ("input_model", dict), ("output_model", "model.path"),
    ("output_model", ExampleOutput(count=1)),
])
def test_invalid_contract_data_is_rejected(field, value):
    with pytest.raises(ValidationError):
        ToolSpecV2(**(spec_payload() | {field: value}))


@pytest.mark.parametrize("seconds", [0.01, 1, 30.0])
def test_timeout_is_positive_finite_numeric_data(seconds):
    assert ToolSpecV2(**(spec_payload() | {"timeout_seconds": seconds})).timeout_seconds == seconds


@pytest.mark.parametrize("field", ["reversible", "idempotent", "supports_dry_run"])
@pytest.mark.parametrize("value", [0, 1, "true", None])
def test_boolean_metadata_is_strict(field, value):
    with pytest.raises(ValidationError):
        ToolSpecV2(**(spec_payload() | {field: value}))


def test_fields_are_explicit_frozen_and_extra_authority_is_rejected():
    spec = ToolSpecV2(**spec_payload())
    for field in ToolSpecV2.model_fields:
        missing = spec_payload()
        del missing[field]
        with pytest.raises(ValidationError, match="Field required"):
            ToolSpecV2(**missing)
        with pytest.raises(ValidationError, match="frozen"):
            setattr(spec, field, getattr(spec, field))
    for field in ("execute", "requires_approval", "available", "provider", "policy"):
        with pytest.raises(ValidationError, match="Extra inputs"):
            ToolSpecV2(**(spec_payload() | {field: True}))


def test_model_references_are_typed_but_never_instantiated_or_validated_as_payloads():
    class Input(BaseModel):
        query: str

        @model_validator(mode="before")
        @classmethod
        def must_not_run(cls, value):
            raise AssertionError("Spec validation must not execute payload validators")

    class Output(BaseModel):
        count: int

    spec = ToolSpecV2(**(spec_payload() | {"input_model": Input, "output_model": Output}))
    assert spec.input_model is Input
    assert spec.output_model is Output
    assert ToolSpecV2.model_validate(spec.model_dump()) == spec
    invalid = spec.model_copy(update={"timeout_seconds": 0})
    with pytest.raises(ValidationError):
        ToolSpecV2.model_validate(invalid)
