from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SessionCreateResponse(BaseModel):
    session_id: str


class MessageRecord(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: str


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    run_id: str


class ApprovalRecord(BaseModel):
    id: str
    session_id: str
    run_id: str
    tool_name: str
    tool_input: dict[str, Any]
    status: Literal["pending", "approved", "denied"]
    requested_at: str


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "deny"]


class ApprovalDecisionResponse(BaseModel):
    ok: bool
    approval_id: str
    status: Literal["approved", "denied"]


class JarvisSettings(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_name: str
    language: str
    ollama_base_url: str
    tts_engine: str
    tts_model_path: str
    tts_voice: str
    say_rate_wpm: int = 235
    tts_sir_pronunciation: str = "Sör"
    whisper_model_path: str
    whisper_binary: str
    allowed_paths: list[str]


class JarvisSettingsUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_name: str | None = None
    language: str | None = None
    ollama_base_url: str | None = None
    tts_engine: str | None = None
    tts_model_path: str | None = None
    tts_voice: str | None = None
    say_rate_wpm: int | None = None
    tts_sir_pronunciation: str | None = None
    whisper_model_path: str | None = None
    whisper_binary: str | None = None
    allowed_paths: list[str] | None = None


class TranscriptionResponse(BaseModel):
    text: str
    language: str
    latency_ms: int


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1)


class SpeakResponse(BaseModel):
    ok: bool
    duration_ms: int


class SmartHomeEntity(BaseModel):
    id: str
    entity_type: str
    name: str
    state: str
    attributes: dict[str, Any]


class SmartHomeCallRequest(BaseModel):
    entity_id: str
    service: str


class StreamRunStateEvent(BaseModel):
    event: Literal["run_state"]
    run_id: str
    state: Literal[
        "received",
        "thinking",
        "approval_required",
        "executing",
        "done",
        "error",
    ]
    detail: str | None = None
    timestamp: str
    data: dict[str, Any] | None = None


class StreamTokenEvent(BaseModel):
    event: Literal["token"]
    run_id: str
    token: str
    timestamp: str


class StreamMessageEvent(BaseModel):
    event: Literal["message"]
    run_id: str
    role: Literal["assistant"]
    content: str
    timestamp: str
