"""An inert, normalized capability request; no registry lookup or execution."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import StrictBool, StringConstraints

from .common import DomainId, DomainModel, JsonObject


class ActionMode(StrEnum):
    READ = "read"
    WRITE = "write"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    SYSTEM = "system"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


CapabilityName = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"),
]


class Action(DomainModel):
    """Metadata is explicit data, never a policy verdict or a tool permission."""

    id: DomainId
    capability: CapabilityName
    arguments: JsonObject
    mode: ActionMode
    risk: RiskLevel
    reversible: StrictBool
    requires_result: StrictBool
