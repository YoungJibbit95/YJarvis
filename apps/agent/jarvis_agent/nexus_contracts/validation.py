"""Stateless DTO validation. A valid record proves no runtime behavior."""

from types import MappingProxyType
from typing import NamedTuple

from pydantic import TypeAdapter

from . import messages as m
from . import primitives as p
from . import types as t
from .canonical import canonical_bytes
from .constants import MAX_DOCUMENT_BYTES, WriteMethod

CONTRACT_TYPES = MappingProxyType({
    "Account": t.Account, "ActionIdentity": t.ActionIdentity[WriteMethod],
    "CapabilitiesRequest": m.CapabilitiesRequest, "CapabilitiesResponse": m.CapabilitiesResponse,
    "Capability": t.Capability, "CreateMutation": t.CreateMutation,
    "CreatePreconditions": t.CreatePreconditions, "CursorBinding": t.CursorBinding,
    "Deadline": t.Deadline, "Digest": p.Digest, "EntityRef": t.EntityRef,
    "FluxMetadata": t.FluxMetadata, "FluxRequest": m.FluxRequest, "FluxResponse": m.FluxResponse,
    "HelloRequest": m.HelloRequest, "HelloResponse": m.HelloResponse, "Id": p.Id,
    "Instant": p.Instant, "MagicDescriptorV1": t.MagicDescriptorV1, "MagicField": t.MagicField,
    "MutationStatusRequest": m.MutationStatusRequest, "MutationStatusResponse": m.MutationStatusResponse,
    "MutationStatusResult": t.MutationStatusResult, "NoteMetadata": t.NoteMetadata,
    "NotesCreateRequest": m.NotesCreateRequest, "NotesCreateResponse": m.NotesCreateResponse,
    "NotesQueryRequest": m.NotesQueryRequest, "NotesQueryResponse": m.NotesQueryResponse,
    "PlanningMetadata": t.PlanningMetadata, "PlanningQueryRequest": m.PlanningQueryRequest,
    "PlanningQueryResponse": m.PlanningQueryResponse, "ReadWarning": t.ReadWarning,
    "Receipt": t.Receipt, "ReceiptRevision": t.ReceiptRevision,
    "ReminderMetadata": t.ReminderMetadata, "RemindersQueryRequest": m.RemindersQueryRequest,
    "RemindersQueryResponse": m.RemindersQueryResponse, "Request": m.Request, "Response": m.Response,
    "RuntimeContext": t.RuntimeContext, "Scope": t.Scope, "SideEffect": t.SideEffect,
    "TaskMetadata": t.TaskMetadata, "TasksCreateRequest": m.TasksCreateRequest,
    "TasksCreateResponse": m.TasksCreateResponse, "TasksQueryRequest": m.TasksQueryRequest,
    "TasksQueryResponse": m.TasksQueryResponse, "TimeZone": p.TimeZone, "Title": p.Title,
})
_ADAPTERS = MappingProxyType({name: TypeAdapter(model) for name, model in CONTRACT_TYPES.items()})


class ContractValidationError(ValueError):
    """A document violates the inert contract, not an execution failure."""


class Validation(NamedTuple):
    valid: bool


def parse_contract(name: str, value: object) -> object:
    """Validate one named contract and return typed data; no retries or effects."""
    adapter = _ADAPTERS[name]  # Unknown schema names are programming errors.
    try:
        if len(canonical_bytes(value)) > MAX_DOCUMENT_BYTES:
            raise ContractValidationError("maxDocumentBytes")
        return adapter.validate_python(value, strict=True)
    except (ValueError, OverflowError, RecursionError) as error:
        raise ContractValidationError(str(error)) from error


def validate_contract(name: str, value: object) -> Validation:
    """Only structural validity; never grants, freshness, persistence or dedupe."""
    try:
        parse_contract(name, value)
    except ContractValidationError:
        return Validation(False)
    return Validation(True)
