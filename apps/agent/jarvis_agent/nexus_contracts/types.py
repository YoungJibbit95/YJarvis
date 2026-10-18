"""Closed, stateless Nexus DTOs. None of these records grants authority."""

from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_serializer, model_validator

from .constants import CAPABILITY_MAPPING, CapabilityName, Method, WriteMethod
from .primitives import (
    BoundedLength, CursorText, Date, Digest, FiniteNumber, Id, Instant, SafeInteger,
    Tags, Text, TimeZone, Title, UniqueList, FalseValue, TrueValue, json_integer,
)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        strict=True, extra="forbid", frozen=True, revalidate_instances="always",
        allow_inf_nan=False,
    )

    @model_validator(mode="wrap")
    @classmethod
    def _revalidate_present_fields(cls, value, handler):
        if isinstance(value, cls):
            value = value.to_wire()
        return handler(value)

    @model_serializer(mode="wrap")
    def _serialize_present_fields(self, handler):
        # TS optional means absent, not nullable. Omitted Python defaults are
        # never inserted into wire objects, including nested serialization.
        return {key: value for key, value in handler(self).items() if key in self.model_fields_set}

    def to_wire(self) -> dict:
        return self.model_dump(mode="python")


class LibraryScope(ContractModel):
    kind: Literal["library"]


class WorkspaceScope(ContractModel):
    kind: Literal["workspace"]
    workspaceId: Id


Scope = LibraryScope | WorkspaceScope


class AnonymousAccount(ContractModel):
    mode: Literal["anonymous-local"]


class AuthenticatedAccount(ContractModel):
    mode: Literal["authenticated"]
    subject: Id


Account = AnonymousAccount | AuthenticatedAccount


class RuntimeContext(ContractModel):
    instanceId: Id
    rendererEpoch: Id
    runtimeGeneration: Id
    sessionId: Id
    bridgeProfileId: Id
    account: Account
    scope: Scope


class DomainEntityRef(ContractModel):
    kind: Literal["note", "task", "reminder", "canvas", "planning-event", "planning-block"]
    id: Id


class CanvasNodeRef(ContractModel):
    kind: Literal["canvas-node"]
    canvasId: Id
    id: Id


EntityRef = DomainEntityRef | CanvasNodeRef
W = TypeVar("W", bound=WriteMethod)


class ActionIdentity(ContractModel, Generic[W]):
    actionId: Id
    clientId: Id
    idempotencyKey: Id
    argumentsDigest: Digest
    origin: RuntimeContext
    method: W


class CreatePreconditions(ContractModel):
    planningRevision: SafeInteger


class CreateMutation(ContractModel):
    actionId: Id
    clientId: Id
    idempotencyKey: Id
    argumentsDigest: Digest
    preconditions: CreatePreconditions


class SideEffect(ContractModel):
    kind: Literal["native_delivery"]
    entity: EntityRef
    state: Literal["pending", "unknown"]


class ReceiptRevision(ContractModel):
    source: Literal["planning-document"]
    value: SafeInteger


class ReceiptFields(ContractModel, Generic[W]):
    entities: Annotated[UniqueList[EntityRef], Field(min_length=1, max_length=32)]
    revision: ReceiptRevision
    acknowledgedAt: Instant
    retainedUntil: Instant
    replayed: bool
    action: ActionIdentity[W]


class AcknowledgedReceipt(ReceiptFields[W], Generic[W]):
    status: Literal["acknowledged"]
    sideEffects: Annotated[list[SideEffect], Field(max_length=0)]


class PendingEffectReceipt(ReceiptFields[W], Generic[W]):
    status: Literal["completed_with_pending_side_effect"]
    sideEffects: Annotated[list[SideEffect], Field(min_length=1, max_length=32)]


Receipt = AcknowledgedReceipt[WriteMethod] | PendingEffectReceipt[WriteMethod]


class CursorBinding(ContractModel):
    clientId: Id
    grantId: Id
    context: RuntimeContext
    queryFingerprint: Digest
    membershipFingerprint: Digest
    snapshotEpoch: Digest
    nextPosition: SafeInteger
    expiresAt: Instant


class TextMagicField(ContractModel):
    key: Id
    type: Literal["string", "datetime", "entity-ref"]
    required: bool
    multiline: bool
    minLength: BoundedLength
    maxLength: BoundedLength


class EnumMagicField(ContractModel):
    key: Id
    type: Literal["enum"]
    required: bool
    values: Annotated[UniqueList[Annotated[Text, Field(max_length=512)]], Field(min_length=1, max_length=64)]


class NumberMagicField(ContractModel):
    key: Id
    type: Literal["number"]
    required: bool
    minimum: FiniteNumber
    maximum: FiniteNumber


class BooleanMagicField(ContractModel):
    key: Id
    type: Literal["boolean"]
    required: bool


MagicField = TextMagicField | EnumMagicField | NumberMagicField | BooleanMagicField


class MagicDescriptorV1(ContractModel):
    id: Id
    version: Annotated[Literal[1], BeforeValidator(json_integer)]
    schemaHash: Digest
    syntaxKind: Literal["fenced", "inline", "planning-linked"]
    label: Title
    description: Annotated[Text, Field(max_length=2048)]
    fields: Annotated[list[MagicField], Field(max_length=32)]
    serializerVersion: Id
    persistence: Literal["preview_only", "persistent", "domain_linked"]
    supportedMethods: Annotated[UniqueList[Method], Field(max_length=10)]
    sideEffects: Annotated[UniqueList[Literal["task_creation", "reminder_creation"]], Field(max_length=2)]
    supportedClients: Annotated[UniqueList[Literal["main", "mobile"]], Field(min_length=1, max_length=2)]
    dependencies: Annotated[UniqueList[Id], Field(max_length=32)]


class Capability(ContractModel):
    method: Method
    capability: CapabilityName
    schemaId: Literal["urn:nexus:local:wire:2.0.0"]
    schemaVersion: Literal["2.0.0"]
    schemaHash: Digest
    nexusState: Literal["known", "offered", "ready", "authorized"]

    @model_validator(mode="after")
    def _correlated_capability(self):
        if self.capability != CAPABILITY_MAPPING[self.method]:
            raise ValueError("Method/capability mismatch")
        return self


class CivilDeadline(ContractModel):
    date: Date
    timeZone: TimeZone


Deadline = Instant | CivilDeadline | None


class NoteMetadata(ContractModel):
    id: Id
    title: Title = Field(default=None)
    tags: Tags = Field(default=None)
    updated: Instant = Field(default=None)


class TaskMetadata(ContractModel):
    id: Id
    title: Title = Field(default=None)
    status: Literal["todo", "doing", "done"] = Field(default=None)
    priority: Literal["low", "mid", "high"] = Field(default=None)
    deadline: Deadline = None
    updated: Instant = Field(default=None)


class ReminderMetadata(ContractModel):
    id: Id
    title: Title = Field(default=None)
    datetime: Instant = Field(default=None)
    repeat: Literal["none", "daily", "weekly", "monthly"] = Field(default=None)
    done: bool = Field(default=None)
    snoozeUntil: Instant | None = None


class PlanningEvent(ContractModel):
    kind: Literal["event"]
    id: Id
    title: Title
    start: Instant
    end: Instant
    timeZone: TimeZone


class TaskRef(ContractModel):
    kind: Literal["task"]
    id: Id


class PlanningBlock(ContractModel):
    kind: Literal["block"]
    id: Id
    task: TaskRef
    start: Instant
    end: Instant
    timeZone: TimeZone


PlanningMetadata = PlanningEvent | PlanningBlock


class FluxMetadata(ContractModel):
    entity: EntityRef
    title: Title
    reasons: Annotated[
        UniqueList[Literal["overdue", "due-soon", "high-priority", "blocked", "unresolved", "unplanned", "conflict"]],
        Field(min_length=1, max_length=7),
    ]


class ReadWarning(ContractModel):
    code: Literal["unresolved"]
    entity: EntityRef


Item = TypeVar("Item")


class SnapshotFields(ContractModel, Generic[Item]):
    consistency: Literal["current"]
    durability: Literal["queued", "acknowledged", "unknown"]
    snapshotEpoch: Digest
    data: Annotated[list[Item], Field(max_length=100)]
    warnings: Annotated[list[ReadWarning], Field(max_length=100)]


class UnpagedSnapshot(SnapshotFields[Item], Generic[Item]):
    truncated: FalseValue
    nextCursor: None


class PagedSnapshot(SnapshotFields[Item], Generic[Item]):
    truncated: TrueValue
    nextCursor: CursorText | None


class TruncatedFluxSnapshot(SnapshotFields[FluxMetadata]):
    data: Annotated[list[FluxMetadata], Field(min_length=1, max_length=100)]
    truncated: TrueValue
    nextCursor: None


class AcknowledgedStatus(ContractModel):
    state: Literal["acknowledged"]
    receipt: AcknowledgedReceipt[WriteMethod]


class PendingEffectStatus(ContractModel):
    state: Literal["completed_with_pending_side_effect"]
    receipt: PendingEffectReceipt[WriteMethod]


class UncertainStatus(ContractModel):
    state: Literal["not_found", "recovery_pending", "expired_or_unknown", "unknown_outcome"]
    action: ActionIdentity[WriteMethod]


MutationStatusResult = AcknowledgedStatus | PendingEffectStatus | UncertainStatus
