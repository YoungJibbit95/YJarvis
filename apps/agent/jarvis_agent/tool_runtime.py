"""Unwired semantic execution kernel; validation is not authorization or outcome."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from .domain.action import CapabilityName
from .domain.capability_catalog import CAPABILITY_CATALOG


class ToolProvider(Protocol):
    """Injected async boundary; no discovery, availability or OS implementation."""

    async def execute(self, capability: CapabilityName, input_data: BaseModel) -> object:
        """Return data for output validation; propagate failures to the caller."""
        ...


class ToolRuntime:
    """Validate, invoke once, validate; no policy, timeout or result normalization."""

    def __init__(self, provider: ToolProvider) -> None:
        self._provider = provider

    async def execute(self, capability: CapabilityName, raw_input: object) -> BaseModel:
        """Return typed data, including an empty NoDataOutput, never proof of success.

        Unknown keys raise KeyError. Pydantic and provider exceptions pass through
        unchanged. Both contracts must exist before the provider can be invoked.
        """
        spec = CAPABILITY_CATALOG[capability]
        if spec.input_model is None or spec.output_model is None:
            raise TypeError(f"Capability {capability!r} requires input and output contracts")
        input_data = spec.input_model.model_validate(raw_input)
        output_data = await self._provider.execute(capability, input_data)
        return spec.output_model.model_validate(output_data)
