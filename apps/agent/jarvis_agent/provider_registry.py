"""Explicit semantic provider registration; known does not mean available."""

from __future__ import annotations

from pydantic import BaseModel

from .domain.action import CapabilityName
from .domain.capability_catalog import CAPABILITY_CATALOG
from .tool_runtime import ToolProvider


class CapabilityUnavailableError(LookupError):
    """The capability is known, but this registry has no registered provider."""

    def __init__(self, capability: CapabilityName) -> None:
        self.capability = capability
        super().__init__(f"No provider registered for capability {capability!r}")


class CapabilityProviderRegistry:
    """A ToolProvider composition boundary, without discovery or authorization.

    Availability means explicit registration, not provider health or permission.
    Input/output validation remains the responsibility of the ToolRuntime caller.
    """

    def __init__(self) -> None:
        self._providers: dict[CapabilityName, ToolProvider] = {}

    def register(self, capability: CapabilityName, provider: ToolProvider) -> None:
        """Register a known key once; unknown keys and duplicates fail unchanged."""
        CAPABILITY_CATALOG[capability]
        if capability in self._providers:
            raise ValueError(f"Provider already registered for capability {capability!r}")
        self._providers[capability] = provider

    def resolve(self, capability: CapabilityName) -> ToolProvider:
        """Return the exact provider; distinguish unknown from unavailable keys."""
        CAPABILITY_CATALOG[capability]
        try:
            return self._providers[capability]
        except KeyError:
            raise CapabilityUnavailableError(capability) from None

    def available_capabilities(self) -> tuple[CapabilityName, ...]:
        """Return an immutable, lexically sorted snapshot of registered keys."""
        return tuple(sorted(self._providers))

    async def execute(self, capability: CapabilityName, input_data: BaseModel) -> object:
        """Delegate once, preserving typed input, raw output and provider errors."""
        return await self.resolve(capability).execute(capability, input_data)
