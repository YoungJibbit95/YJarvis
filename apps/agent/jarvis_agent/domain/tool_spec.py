"""Descriptive, code-local capability metadata; never execution or policy authority."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, StrictBool

from .action import ActionMode, CapabilityName, RiskLevel
from .common import DomainModel, NonBlankText


class ToolSpecV2(DomainModel):
    """A known capability, not proof that a provider exists on this machine.

    Model references are Python classes, never instantiated here. None explicitly
    means the input/output contract is not modeled yet, not an empty/free-form
    schema. These records are code metadata, not wire or persistence DTOs.
    """

    capability: CapabilityName
    description: NonBlankText
    input_model: type[BaseModel] | None
    output_model: type[BaseModel] | None
    mode: ActionMode
    default_risk: RiskLevel
    reversible: StrictBool
    idempotent: StrictBool
    supports_dry_run: StrictBool
    timeout_seconds: Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
