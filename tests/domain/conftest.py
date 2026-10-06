"""Deterministic domain fixtures: no clocks, UUID generation, services or models."""

from copy import deepcopy
from uuid import UUID

import pytest


@pytest.fixture
def action_payload():
    return {
        "id": str(UUID(int=1)),
        "capability": "example.first",
        "arguments": {"title": "Projekt Review", "duration_minutes": 30},
        "mode": "write",
        "risk": "medium",
        "reversible": True,
        "requires_result": True,
    }


@pytest.fixture
def turn_payload():
    return {
        "id": str(UUID(int=10)),
        "session_id": str(UUID(int=11)),
        "input_mode": "text",
        "user_text": "  Plane mein Projekt-Review.  ",
        "created_at": "2026-10-06T17:00:00+00:00",
        "updated_at": "2026-10-06T19:00:00+02:00",
    }


@pytest.fixture
def plan_payload(action_payload):
    second = deepcopy(action_payload)
    second.update(id=str(UUID(int=2)), capability="example.second")
    return {
        "id": str(UUID(int=20)),
        "turn_id": str(UUID(int=10)),
        "goal": "Prepare the review",
        "summary": "Create a review and its dependent reminder",
        "actions": [
            {"action": action_payload},
            {"action": second, "depends_on": [action_payload["id"]]},
        ],
    }


@pytest.fixture
def policy_payload():
    return {
        "action_id": str(UUID(int=1)),
        "verdict": "confirm",
        "reason_code": "EXPLICIT_CONSENT",
        "human_reason": "This action requires confirmation.",
        "policy_source": "test-fixture",
    }


@pytest.fixture
def observation_payload():
    return {
        "action_id": str(UUID(int=1)),
        "success": True,
        "summary": "Recorded result",
        "data": {"item_id": "example-only"},
        "duration_ms": 0,
        "occurred_at": "2026-10-06T19:01:00+02:00",
    }
