from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .agent_service import AgentService
from .audio import AudioError, list_say_voices, speak_text, transcribe_with_whisper_cpp
from .config import ensure_runtime_dirs, load_config
from .db import Database
from .events import EventBus
from .profile import ensure_profile
from .schemas import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalRecord,
    ChatRequest,
    ChatResponse,
    JarvisSettings,
    JarvisSettingsUpdate,
    MessageRecord,
    SessionCreateResponse,
    SmartHomeCallRequest,
    SmartHomeEntity,
    SpeakRequest,
    SpeakResponse,
    TranscriptionResponse,
)
from .smarthome import HomeAssistantStubProvider
from .setup_api import create_setup_router
from .tools import ToolRegistry

config = load_config()
ensure_runtime_dirs(config)

database = Database(
    db_path=config.db_path,
    project_root=config.project_root,
    default_whisper_model=config.default_whisper_model,
)
event_bus = EventBus()
tool_registry = ToolRegistry()
agent_service = AgentService(
    database,
    event_bus,
    tool_registry,
    profile_path=config.profile_path,
)
smarthome_provider = HomeAssistantStubProvider(database)

app = FastAPI(title="Jarvis Local Agent", version="0.1.0")
app.include_router(create_setup_router(database.get_settings, config.default_whisper_model, config.runtime_dir))

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "app://yjarvis",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    await database.init()
    ensure_profile(config.profile_path)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/sessions", response_model=SessionCreateResponse)
async def create_session() -> SessionCreateResponse:
    session_id = str(uuid.uuid4())
    await database.create_session(session_id)
    return SessionCreateResponse(session_id=session_id)


@app.get("/v1/sessions/{session_id}/messages", response_model=list[MessageRecord])
async def list_messages(session_id: str) -> list[MessageRecord]:
    exists = await database.session_exists(session_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Session nicht gefunden")

    rows = await database.list_messages(session_id)
    return [MessageRecord(**row) for row in rows]


@app.websocket("/v1/ws/{session_id}")
async def websocket_stream(session_id: str, websocket: WebSocket) -> None:
    await event_bus.connect(session_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await event_bus.disconnect(session_id, websocket)
    except Exception:
        await event_bus.disconnect(session_id, websocket)


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    exists = await database.session_exists(request.session_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Session nicht gefunden")

    run_id = str(uuid.uuid4())
    agent_service.start_run_background(
        session_id=request.session_id,
        run_id=run_id,
        user_message=request.message,
    )

    return ChatResponse(run_id=run_id)


@app.get("/v1/approvals/pending", response_model=list[ApprovalRecord])
async def list_pending_approvals() -> list[ApprovalRecord]:
    approvals = await database.list_pending_approvals()
    return [ApprovalRecord(**row) for row in approvals]


@app.post("/v1/approvals/{approval_id}", response_model=ApprovalDecisionResponse)
async def decide_approval(
    approval_id: str,
    request: ApprovalDecisionRequest,
) -> ApprovalDecisionResponse:
    try:
        status = await agent_service.handle_approval_decision(approval_id, request.decision)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    normalized_status = "approved" if status == "approved" else "denied"
    return ApprovalDecisionResponse(ok=True, approval_id=approval_id, status=normalized_status)


@app.get("/v1/settings", response_model=JarvisSettings)
async def get_settings() -> JarvisSettings:
    settings = await database.get_settings()
    return JarvisSettings(**settings)


@app.put("/v1/settings", response_model=JarvisSettings)
async def update_settings(payload: JarvisSettingsUpdate) -> JarvisSettings:
    update_data = payload.model_dump(exclude_none=True)
    updated = await database.update_settings(update_data)
    return JarvisSettings(**updated)


@app.post("/v1/audio/transcribe", response_model=TranscriptionResponse)
async def transcribe(file: UploadFile = File(...)) -> TranscriptionResponse:
    suffix = Path(file.filename or "upload.bin").suffix or ".bin"
    file_path = config.audio_tmp_dir / f"upload-{uuid.uuid4().hex}{suffix}"
    file_path.write_bytes(await file.read())

    try:
        settings = await database.get_settings()
        text, language, latency_ms = await transcribe_with_whisper_cpp(
            source_path=file_path,
            settings=settings,
            config=config,
        )
        return TranscriptionResponse(text=text, language=language, latency_ms=latency_ms)
    except AudioError as error:
        detail = " ".join(str(error).split()).strip()
        if len(detail) > 280:
            detail = detail[:277] + "..."
        raise HTTPException(status_code=503, detail=detail) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Transcription Fehler: {error}") from error
    finally:
        try:
            await file.close()
        except Exception:
            pass
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.get("/v1/audio/voices", response_model=list[str])
async def list_audio_voices() -> list[str]:
    try:
        return await list_say_voices()
    except AudioError as error:
        detail = " ".join(str(error).split()).strip()
        if len(detail) > 280:
            detail = detail[:277] + "..."
        raise HTTPException(status_code=503, detail=detail) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Voice-Liste Fehler: {error}") from error


@app.post("/v1/audio/speak", response_model=SpeakResponse)
async def speak(request: SpeakRequest) -> SpeakResponse:
    settings = await database.get_settings()
    try:
        duration_ms = await speak_text(text=request.text, settings=settings, config=config)
    except AudioError as error:
        detail = " ".join(str(error).split()).strip()
        if len(detail) > 280:
            detail = detail[:277] + "..."
        raise HTTPException(status_code=503, detail=detail) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"TTS Fehler: {error}") from error

    return SpeakResponse(ok=True, duration_ms=duration_ms)


@app.get("/v1/smarthome/entities", response_model=list[SmartHomeEntity])
async def list_smarthome_entities() -> list[SmartHomeEntity]:
    entities = await smarthome_provider.list_entities()
    return [SmartHomeEntity(**entity) for entity in entities]


@app.post("/v1/smarthome/call", response_model=SmartHomeEntity)
async def call_smarthome_service(request: SmartHomeCallRequest) -> SmartHomeEntity:
    try:
        entity = await smarthome_provider.call_service(
            entity_id=request.entity_id,
            service=request.service,
        )
        return SmartHomeEntity(**entity)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
