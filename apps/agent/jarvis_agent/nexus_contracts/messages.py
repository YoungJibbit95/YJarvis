"""Exactly ten closed request/response families; no dispatch or provider code."""

from typing import Annotated, Generic, Literal, TypeVar

from pydantic import Field

from .constants import ErrorStatus, Method, WriteMethod
from .primitives import CursorText, Duration, Id, Instant, PageLimit, SchemaVersionText, Tags, Text, TimeZone, Title, UniqueList
from .types import (
    AcknowledgedReceipt, ActionIdentity, Capability, ContractModel, CreateMutation,
    Deadline, FluxMetadata, MagicDescriptorV1, MutationStatusResult, NoteMetadata,
    PagedSnapshot, PendingEffectReceipt, PlanningMetadata, ReminderMetadata, RuntimeContext,
    TaskMetadata, TruncatedFluxSnapshot, UnpagedSnapshot,
)

M = TypeVar("M", bound=Method)
W = TypeVar("W", bound=WriteMethod)
P = TypeVar("P")
D = TypeVar("D")


class Envelope(ContractModel):
    protocolVersion: Literal["nexus.local.v1"]
    schemaVersion: Literal["2.0.0"]
    requestId: Id


class EmptyParams(ContractModel):
    pass


class HelloParams(ContractModel):
    supportedSchemaVersions: Annotated[UniqueList[SchemaVersionText], Field(min_length=1, max_length=8)]


class HelloRequest(Envelope):
    method: Literal["system.hello"]
    params: HelloParams


class ContextRequest(Envelope, Generic[M, P]):
    method: M
    context: RuntimeContext
    params: P


class WriteRequest(ContextRequest[W, P], Generic[W, P]):
    mutation: CreateMutation


class MutationStatusParams(ContractModel):
    action: ActionIdentity[WriteMethod]


F = TypeVar("F")


class QueryParams(ContractModel, Generic[F]):
    readConsistency: Literal["current"]
    limit: PageLimit
    fields: Annotated[UniqueList[F], Field(min_length=1)]
    query: Annotated[Text, Field(max_length=256)] = Field(default=None)
    cursor: CursorText | None = None


class NotesQueryParams(QueryParams[Literal["id", "title", "tags", "updated"]]):
    fields: Annotated[UniqueList[Literal["id", "title", "tags", "updated"]], Field(min_length=1, max_length=4)]


class TasksQueryParams(QueryParams[Literal["id", "title", "status", "priority", "deadline", "updated"]]):
    fields: Annotated[UniqueList[Literal["id", "title", "status", "priority", "deadline", "updated"]], Field(min_length=1, max_length=6)]


class RemindersQueryParams(QueryParams[Literal["id", "title", "datetime", "repeat", "done", "snoozeUntil"]]):
    fields: Annotated[UniqueList[Literal["id", "title", "datetime", "repeat", "done", "snoozeUntil"]], Field(min_length=1, max_length=6)]


class PlanningQueryParams(ContractModel):
    readConsistency: Literal["current"]
    start: Instant
    end: Instant
    timeZone: TimeZone
    limit: PageLimit
    cursor: CursorText | None = None


class FluxParams(ContractModel):
    readConsistency: Literal["current"]
    now: Instant
    timeZone: TimeZone
    limit: PageLimit


class NotesCreateParams(ContractModel):
    title: Title
    content: Annotated[Text, Field(max_length=65_536)]
    tags: Tags = Field(default=None)


class TasksCreateParams(ContractModel):
    title: Title
    desc: Annotated[Text, Field(max_length=8192)] = Field(default=None)
    priority: Literal["low", "mid", "high"] = Field(default=None)
    durationMinutes: Duration = Field(default=None)
    deadline: Deadline = None
    tags: Tags = Field(default=None)


CapabilitiesRequest = ContextRequest[Literal["capabilities.list"], EmptyParams]
MutationStatusRequest = ContextRequest[Literal["mutation.status"], MutationStatusParams]
NotesQueryRequest = ContextRequest[Literal["notes.query"], NotesQueryParams]
TasksQueryRequest = ContextRequest[Literal["tasks.query"], TasksQueryParams]
RemindersQueryRequest = ContextRequest[Literal["reminders.query"], RemindersQueryParams]
PlanningQueryRequest = ContextRequest[Literal["planning.queryRange"], PlanningQueryParams]
FluxRequest = ContextRequest[Literal["flux.getAttention"], FluxParams]
NotesCreateRequest = WriteRequest[Literal["notes.create"], NotesCreateParams]
TasksCreateRequest = WriteRequest[Literal["tasks.create"], TasksCreateParams]
Request = (
    HelloRequest | CapabilitiesRequest | MutationStatusRequest | NotesQueryRequest
    | TasksQueryRequest | RemindersQueryRequest | PlanningQueryRequest | FluxRequest
    | NotesCreateRequest | TasksCreateRequest
)


class ErrorDetail(ContractModel):
    message: Annotated[Text, Field(min_length=1, max_length=512)]


class Failure(Envelope, Generic[M]):
    method: M
    status: ErrorStatus
    error: ErrorDetail


class Success(Envelope, Generic[M, D]):
    method: M
    status: Literal["accepted"]
    context: RuntimeContext
    data: D


class HelloData(ContractModel):
    instanceId: Id
    supportedProtocolVersions: Annotated[list[Literal["nexus.local.v1"]], Field(min_length=1, max_length=1)]
    supportedSchemaVersions: Annotated[list[Literal["2.0.0"]], Field(min_length=1, max_length=1)]
    state: Literal["STARTING", "NOT_READY", "NOT_PAIRED", "LOCKED", "RECOVERY_PENDING", "READY"]


class HelloSuccess(Envelope):
    method: Literal["system.hello"]
    status: Literal["accepted"]
    data: HelloData


class CapabilitiesData(ContractModel):
    capabilities: Annotated[list[Capability], Field(max_length=10)]
    magicDescriptors: Annotated[list[MagicDescriptorV1], Field(max_length=32)]


class PlanningData(ContractModel):
    snapshot: UnpagedSnapshot[PlanningMetadata] | PagedSnapshot[PlanningMetadata]
    coverage: Literal["known", "unknown"]


class FluxData(ContractModel):
    snapshot: UnpagedSnapshot[FluxMetadata] | TruncatedFluxSnapshot
    now: Instant
    timeZone: TimeZone


class WriteAccepted(Envelope, Generic[W]):
    method: W
    status: Literal["accepted"]
    context: RuntimeContext
    action: ActionIdentity[W]


class WriteAcknowledged(Envelope, Generic[W]):
    method: W
    status: Literal["acknowledged"]
    context: RuntimeContext
    receipt: AcknowledgedReceipt[W]


class WritePending(Envelope, Generic[W]):
    method: W
    status: Literal["completed_with_pending_side_effect"]
    context: RuntimeContext
    receipt: PendingEffectReceipt[W]


class WriteUnknown(Envelope, Generic[W]):
    method: W
    status: Literal["unknown_outcome"]
    action: ActionIdentity[W]
    error: ErrorDetail


HelloResponse = HelloSuccess | Failure[Literal["system.hello"]]
CapabilitiesResponse = Success[Literal["capabilities.list"], CapabilitiesData] | Failure[Literal["capabilities.list"]]
MutationStatusResponse = Success[Literal["mutation.status"], MutationStatusResult] | Failure[Literal["mutation.status"]]
NotesQueryResponse = Success[Literal["notes.query"], UnpagedSnapshot[NoteMetadata] | PagedSnapshot[NoteMetadata]] | Failure[Literal["notes.query"]]
TasksQueryResponse = Success[Literal["tasks.query"], UnpagedSnapshot[TaskMetadata] | PagedSnapshot[TaskMetadata]] | Failure[Literal["tasks.query"]]
RemindersQueryResponse = Success[Literal["reminders.query"], UnpagedSnapshot[ReminderMetadata] | PagedSnapshot[ReminderMetadata]] | Failure[Literal["reminders.query"]]
PlanningQueryResponse = Success[Literal["planning.queryRange"], PlanningData] | Failure[Literal["planning.queryRange"]]
FluxResponse = Success[Literal["flux.getAttention"], FluxData] | Failure[Literal["flux.getAttention"]]
NotesCreateResponse = (
    WriteAccepted[Literal["notes.create"]] | WriteAcknowledged[Literal["notes.create"]]
    | WritePending[Literal["notes.create"]] | WriteUnknown[Literal["notes.create"]]
    | Failure[Literal["notes.create"]]
)
TasksCreateResponse = (
    WriteAccepted[Literal["tasks.create"]] | WriteAcknowledged[Literal["tasks.create"]]
    | WritePending[Literal["tasks.create"]] | WriteUnknown[Literal["tasks.create"]]
    | Failure[Literal["tasks.create"]]
)
Response = (
    HelloResponse | CapabilitiesResponse | MutationStatusResponse | NotesQueryResponse
    | TasksQueryResponse | RemindersQueryResponse | PlanningQueryResponse | FluxResponse
    | NotesCreateResponse | TasksCreateResponse
)
