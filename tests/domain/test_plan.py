from copy import deepcopy
from uuid import UUID

import pytest
from pydantic import ValidationError

from jarvis_agent.domain import Action, ActionPlan, FailureStrategy, PlannedAction, PlanStatus


def test_valid_dependency_plan_preserves_input_order(plan_payload):
    plan_payload["actions"].reverse()  # A valid forward reference, not a cycle.
    plan = ActionPlan(**plan_payload)
    assert [step.action.id for step in plan.actions] == [UUID(int=2), UUID(int=1)]
    assert plan.actions[0].depends_on == (UUID(int=1),)
    assert plan.status is PlanStatus.DRAFT
    assert plan.actions[0].on_failure is FailureStrategy.STOP
    assert isinstance(plan.actions, tuple)


@pytest.mark.parametrize("status", list(PlanStatus))
def test_status_is_a_snapshot_not_execution_authority(plan_payload, status):
    assert ActionPlan(**{**plan_payload, "status": status}).status is status


@pytest.mark.parametrize("strategy", list(FailureStrategy))
def test_failure_strategy_enum(action_payload, strategy):
    assert PlannedAction(action=action_payload, on_failure=strategy).on_failure is strategy


@pytest.mark.parametrize("value", [[], None, "[]", {}, set()])
def test_rejects_empty_or_unordered_plan_actions(plan_payload, value):
    with pytest.raises(ValidationError):
        ActionPlan(**{**plan_payload, "actions": value})


@pytest.mark.parametrize("value", [{UUID(int=2)}, iter([UUID(int=2)]), "not-an-array", None])
def test_dependencies_require_ordered_sequences(action_payload, value):
    with pytest.raises(ValidationError):
        PlannedAction(action=action_payload, depends_on=value)


def test_rejects_duplicate_action_ids(plan_payload):
    plan_payload["actions"] = [plan_payload["actions"][0], deepcopy(plan_payload["actions"][0])]
    with pytest.raises(ValidationError, match="action IDs must be unique"):
        ActionPlan(**plan_payload)


def test_rejects_duplicate_dependencies_after_uuid_parsing(plan_payload):
    plan_payload["actions"][1]["depends_on"] = [str(UUID(int=1)), UUID(int=1)]
    with pytest.raises(ValidationError, match="duplicate action IDs"):
        ActionPlan(**plan_payload)


def test_rejects_self_reference(action_payload):
    with pytest.raises(ValidationError, match="must not depend on itself"):
        PlannedAction(action=action_payload, depends_on=[action_payload["id"]])


def test_rejects_dangling_or_cross_plan_reference(plan_payload):
    plan_payload["actions"][1]["depends_on"] = [str(UUID(int=999))]
    with pytest.raises(ValidationError, match="outside this plan"):
        ActionPlan(**plan_payload)


def test_rejects_two_action_cycle(plan_payload):
    plan_payload["actions"][0]["depends_on"] = [str(UUID(int=2))]
    with pytest.raises(ValidationError, match="acyclic graph"):
        ActionPlan(**plan_payload)


def test_rejects_cycle_in_disconnected_component(plan_payload, action_payload):
    plan_payload["actions"] = [
        {"action": {**action_payload, "id": str(UUID(int=number))}, "depends_on": dependencies}
        for number, dependencies in [(1, []), (2, [str(UUID(int=3))]), (3, [str(UUID(int=4))]), (4, [str(UUID(int=2))])]
    ]
    with pytest.raises(ValidationError, match="acyclic graph"):
        ActionPlan(**plan_payload)


def test_accepts_diamond_dag_and_disconnected_actions(plan_payload, action_payload):
    graph = [(1, []), (2, [1]), (3, [1]), (4, [2, 3]), (5, [])]
    plan_payload["actions"] = [
        {"action": {**action_payload, "id": str(UUID(int=node))}, "depends_on": [str(UUID(int=dep)) for dep in deps]}
        for node, deps in graph
    ]
    plan = ActionPlan(**plan_payload)
    assert len(plan.actions) == 5
    assert plan.actions[3].depends_on == (UUID(int=2), UUID(int=3))


def test_long_chain_does_not_use_recursive_graph_traversal(plan_payload, action_payload):
    plan_payload["actions"] = [
        {"action": {**action_payload, "id": str(UUID(int=node))}, "depends_on": [str(UUID(int=node - 1))] if node > 1 else []}
        for node in range(1, 1501)
    ]
    assert len(ActionPlan(**plan_payload).actions) == 1500


@pytest.mark.parametrize("field", ["goal", "summary"])
@pytest.mark.parametrize("value", ["", " \n", 3])
def test_plan_descriptions_are_explicit_nonblank_strings(plan_payload, field, value):
    with pytest.raises(ValidationError):
        ActionPlan(**{**plan_payload, field: value})


@pytest.mark.parametrize("field,value", [("status", "ready"), ("status", "APPROVED")])
def test_rejects_unknown_plan_status(plan_payload, field, value):
    with pytest.raises(ValidationError):
        ActionPlan(**{**plan_payload, field: value})


def test_rejects_unknown_failure_strategy(action_payload):
    with pytest.raises(ValidationError):
        PlannedAction(action=action_payload, on_failure="retry_forever")


def test_nested_model_instances_are_revalidated(action_payload, plan_payload):
    invalid_action = Action(**action_payload).model_copy(update={"reversible": "yes"})
    with pytest.raises(ValidationError):
        PlannedAction(action=invalid_action)
    invalid_step = PlannedAction(action=action_payload).model_copy(update={"depends_on": (UUID(int=1),)})
    with pytest.raises(ValidationError, match="must not depend on itself"):
        ActionPlan(**{**plan_payload, "actions": [invalid_step]})


def test_dependency_validation_is_repeatable_and_does_not_mutate_input(plan_payload):
    plan_payload["actions"][0]["depends_on"] = [str(UUID(int=2))]
    original = deepcopy(plan_payload)
    errors = []
    for _ in range(2):
        with pytest.raises(ValidationError) as caught:
            ActionPlan(**plan_payload)
        errors.append(str(caught.value))
    assert errors[0] == errors[1]
    assert plan_payload == original
