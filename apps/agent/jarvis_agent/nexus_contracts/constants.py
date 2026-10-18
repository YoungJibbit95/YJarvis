"""Reviewed wire identifiers, not a capability registry or permission source."""

from types import MappingProxyType
from typing import Literal

PROTOCOL_VERSION = "nexus.local.v1"
SCHEMA_VERSION = FIXTURE_VERSION = "2.0.0"
SCHEMA_ID = "urn:nexus:local:wire:2.0.0"
MAX_DOCUMENT_BYTES = 131_072
MAX_SAFE_INTEGER = 9_007_199_254_740_991

Method = Literal[
    "system.hello", "capabilities.list", "mutation.status", "notes.query",
    "tasks.query", "reminders.query", "planning.queryRange", "flux.getAttention",
    "notes.create", "tasks.create",
]
WriteMethod = Literal["notes.create", "tasks.create"]
CapabilityName = Literal[
    "nexus.system.hello", "nexus.capabilities.list", "nexus.mutation.status",
    "nexus.notes.query", "nexus.tasks.query", "nexus.reminders.query",
    "nexus.planning.queryRange", "nexus.flux.getAttention", "nexus.notes.create",
    "nexus.tasks.create",
]
CAPABILITY_MAPPING = MappingProxyType({
    "system.hello": "nexus.system.hello",
    "capabilities.list": "nexus.capabilities.list",
    "mutation.status": "nexus.mutation.status",
    "notes.query": "nexus.notes.query",
    "tasks.query": "nexus.tasks.query",
    "reminders.query": "nexus.reminders.query",
    "planning.queryRange": "nexus.planning.queryRange",
    "flux.getAttention": "nexus.flux.getAttention",
    "notes.create": "nexus.notes.create",
    "tasks.create": "nexus.tasks.create",
})
METHODS = tuple(CAPABILITY_MAPPING)
ErrorStatus = Literal[
    "validation", "unsupported", "unsupported_scope", "unsupported_consistency",
    "stale", "stale_cursor", "conflict", "denied", "scope_denied", "not_paired",
    "not_ready", "draft_pending", "recovery_pending", "storage_failure",
]
