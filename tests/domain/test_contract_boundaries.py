import json
from copy import deepcopy
from uuid import UUID

import pytest
from pydantic import ValidationError

from jarvis_agent.domain import Action, ActionPlan, Observation, PlannedAction, PolicyDecision, Turn


CONTRACTS = [
    (Action, "action_payload"),
    (ActionPlan, "plan_payload"),
    (Observation, "observation_payload"),
    (PolicyDecision, "policy_payload"),
    (Turn, "turn_payload"),
]


@pytest.mark.parametrize("model,fixture_name", CONTRACTS)
def test_json_and_python_round_trips(model, fixture_name, request):
    payload = request.getfixturevalue(fixture_name)
    instance = model.model_validate(payload)
    assert model.model_validate_json(instance.model_dump_json()) == instance
    assert model.model_validate(instance.model_dump()) == instance
    assert model.model_validate_json(json.dumps(payload)) == instance
    assert model.model_validate(instance) == instance
    assert model.model_validate(payload).model_dump_json() == instance.model_dump_json()
    json.dumps(instance.model_dump(mode="json"), allow_nan=False)


@pytest.mark.parametrize("model,fixture_name", CONTRACTS)
def test_rejects_unknown_fields_at_contract_boundary(model, fixture_name, request):
    payload = {**request.getfixturevalue(fixture_name), "execute_now": True}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        model.model_validate(payload)


@pytest.mark.parametrize("model,fixture_name", CONTRACTS)
def test_every_required_field_rejects_missing_input(model, fixture_name, request):
    payload = request.getfixturevalue(fixture_name)
    for name, field in model.model_fields.items():
        if field.is_required():
            candidate = deepcopy(payload)
            candidate.pop(name)
            with pytest.raises(ValidationError) as caught:
                model.model_validate(candidate)
            assert any(error["loc"] == (name,) and error["type"] == "missing" for error in caught.value.errors())


@pytest.mark.parametrize("model,fixture_name", CONTRACTS)
@pytest.mark.parametrize("value", ["a1", "", "not-a-uuid", 1, None, UUID(int=0), b"00000000-0000-0000-0000-000000000001"])
def test_all_id_fields_require_non_nil_uuids(model, fixture_name, value, request):
    payload = request.getfixturevalue(fixture_name)
    for name in model.model_fields:
        if name == "id" or name.endswith("_id"):
            with pytest.raises(ValidationError):
                model.model_validate({**payload, name: value})


def test_dependency_ids_have_same_uuid_contract(action_payload):
    with pytest.raises(ValidationError):
        PlannedAction(action=action_payload, depends_on=["a2"])
    with pytest.raises(ValidationError):
        PlannedAction(action=action_payload, depends_on=[UUID(int=0)])


@pytest.mark.parametrize("model,fixture_name", CONTRACTS)
def test_attributes_cannot_be_reassigned(model, fixture_name, request):
    instance = model.model_validate(request.getfixturevalue(fixture_name))
    name = next(iter(model.model_fields))
    original = getattr(instance, name)
    with pytest.raises(ValidationError, match="frozen"):
        setattr(instance, name, "invalid")
    assert getattr(instance, name) == original


def test_graph_containers_cannot_be_mutated(plan_payload):
    plan = ActionPlan(**plan_payload)
    with pytest.raises(AttributeError):
        plan.actions.append(plan.actions[0])
    with pytest.raises(AttributeError):
        plan.actions[1].depends_on.append(UUID(int=2))
    with pytest.raises(ValidationError, match="frozen"):
        plan.actions[0].on_failure = "continue"


def test_json_payload_mutation_is_rejected_on_revalidation(plan_payload):
    plan = ActionPlan(**plan_payload)
    # JSON payloads remain normal dict/list data, not a deep-immutable authority.
    plan.actions[0].action.arguments["invalid"] = object()
    with pytest.raises(ValidationError):
        ActionPlan.model_validate(plan)


def test_input_mutation_does_not_change_plan_graph(plan_payload):
    plan = ActionPlan(**plan_payload)
    plan_payload["actions"][1]["depends_on"].clear()
    plan_payload["actions"][0]["action"]["arguments"]["title"] = "changed"
    plan_payload["actions"].clear()
    assert len(plan.actions) == 2
    assert plan.actions[1].depends_on == (UUID(int=1),)
    assert plan.actions[0].action.arguments["title"] == "Projekt Review"


def test_nested_unknown_fields_are_not_silently_discarded(plan_payload):
    plan_payload["actions"][0]["action"]["trusted"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ActionPlan(**plan_payload)
    del plan_payload["actions"][0]["action"]["trusted"]
    plan_payload["actions"][0]["execute_now"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ActionPlan(**plan_payload)


def test_unsafe_pydantic_construction_does_not_bypass_later_validation(action_payload, plan_payload):
    invalid = Action.model_construct(**{**action_payload, "risk": "unknown"})
    with pytest.raises(ValidationError):
        PlannedAction(action=invalid)
    invalid_plan = ActionPlan(**plan_payload).model_copy(update={"actions": ()})
    with pytest.raises(ValidationError):
        ActionPlan.model_validate(invalid_plan)


@pytest.mark.parametrize("model,fixture_name", CONTRACTS)
def test_json_schema_is_available_and_forbids_extra_fields(model, fixture_name):
    schema = model.model_json_schema()
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == set(model.model_fields)
    json.dumps(schema)


def test_plan_schema_exposes_json_arrays_not_python_implementation_details():
    schema = ActionPlan.model_json_schema()
    assert schema["properties"]["actions"]["type"] == "array"
    assert schema["properties"]["actions"]["minItems"] == 1
    assert schema["$defs"]["PlannedAction"]["properties"]["depends_on"]["type"] == "array"
    assert schema["$defs"]["ActionMode"]["enum"] == ["read", "write", "external_side_effect", "system"]
    assert schema["$defs"]["PlanStatus"]["enum"][0] == "draft"
