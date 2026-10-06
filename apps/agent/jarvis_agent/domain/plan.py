"""Plan data and structural DAG validation, not planning or scheduling."""

from __future__ import annotations

from collections import deque
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BeforeValidator, Field, model_validator

from .action import Action
from .common import DomainId, DomainModel, NonBlankText, ordered_sequence


class FailureStrategy(StrEnum):
    STOP = "stop"
    CONTINUE = "continue"
    ASK_USER = "ask_user"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlannedAction(DomainModel):
    """Dependencies identify Action.id values within the containing plan."""

    action: Action
    depends_on: Annotated[tuple[DomainId, ...], BeforeValidator(ordered_sequence)] = ()
    on_failure: FailureStrategy = FailureStrategy.STOP

    @model_validator(mode="after")
    def validate_local_dependencies(self) -> Self:
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("depends_on must not contain duplicate action IDs")
        if self.action.id in self.depends_on:
            raise ValueError("an action must not depend on itself")
        return self


class ActionPlan(DomainModel):
    """A nonempty DAG snapshot. Status labels do not prove authorization.

    Ordered arrays become tuples in Python to prevent unvalidated graph edits;
    they still serialize as JSON arrays. Validation preserves supplied order and
    accepts forward references. A turn needing no actions needs no ActionPlan.
    """

    id: DomainId
    turn_id: DomainId
    goal: NonBlankText
    summary: NonBlankText
    actions: Annotated[
        tuple[PlannedAction, ...], Field(min_length=1), BeforeValidator(ordered_sequence)
    ]
    status: PlanStatus = PlanStatus.DRAFT

    @model_validator(mode="after")
    def validate_dependency_graph(self) -> Self:
        identifiers = [step.action.id for step in self.actions]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("action IDs must be unique within a plan")

        dependents: dict[DomainId, list[DomainId]] = {identifier: [] for identifier in identifiers}
        remaining: dict[DomainId, int] = {}
        for step in self.actions:
            remaining[step.action.id] = len(step.depends_on)
            for dependency in step.depends_on:
                if dependency not in dependents:
                    raise ValueError("depends_on references an action outside this plan")
                dependents[dependency].append(step.action.id)

        # Kahn's algorithm validates in O(V + E) without recursive depth limits.
        # No execution order is returned and the original plan is not reordered.
        ready = deque(identifier for identifier in identifiers if remaining[identifier] == 0)
        visited = 0
        while ready:
            identifier = ready.popleft()
            visited += 1
            for dependent in dependents[identifier]:
                remaining[dependent] -= 1
                if remaining[dependent] == 0:
                    ready.append(dependent)
        if visited != len(identifiers):
            raise ValueError("action dependencies must form an acyclic graph")
        return self
