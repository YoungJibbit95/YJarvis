"""Read-only prerequisite inspection. This never loads a model or invokes audio/tools."""
from __future__ import annotations

import asyncio
import stat
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel

from .native_tools import find_system_tool, find_whisper_binary


class ComponentStatus(BaseModel):
    status: Literal["available", "missing", "unreachable", "unknown", "error"]
    reason: str


class SetupStatus(BaseModel):
    state: Literal["needs_setup", "ready", "degraded", "error"]
    chat_model: ComponentStatus
    stt: ComponentStatus
    tts: ComponentStatus


def model_key(name: str) -> str:
    # Ollama's documented default tag, not fuzzy/substring model matching.
    return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"


def inspect_model_file(value: str | Path) -> ComponentStatus:
    if not value:
        return ComponentStatus(status="missing", reason="path_not_configured")
    try:
        info = Path(value).expanduser().stat()
        if stat.S_ISREG(info.st_mode) and info.st_size > 0:
            return ComponentStatus(status="available", reason="model_file_present")
        return ComponentStatus(status="missing", reason="model_file_invalid")
    except FileNotFoundError:
        return ComponentStatus(status="missing", reason="model_file_missing")
    except (OSError, ValueError, RuntimeError):
        return ComponentStatus(status="unknown", reason="model_file_unreadable")


async def inspect_chat_model(settings: dict[str, Any], client: httpx.AsyncClient) -> ComponentStatus:
    model = str(settings.get("model_name", "")).strip()
    if not model:
        return ComponentStatus(status="missing", reason="chat_model_not_configured")
    base_url = str(settings.get("ollama_base_url", "")).rstrip("/")
    try:
        parsed = urlsplit(base_url)
        _ = parsed.port
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.query or parsed.fragment:
            raise ValueError("Invalid endpoint")
    except ValueError:
        return ComponentStatus(status="error", reason="ollama_endpoint_invalid")
    try:
        url = httpx.URL(f"{base_url}/api/tags")
        if url.scheme not in {"http", "https"} or not url.host:
            return ComponentStatus(status="error", reason="ollama_endpoint_invalid")
        # Bound the whole request, including a peer that slowly streams its response.
        async with asyncio.timeout(4):
            response = await client.get(url)
        if response.status_code != 200:
            return ComponentStatus(status="error", reason="ollama_response_invalid")
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            raise ValueError("Invalid model inventory")
        names: set[str] = set()
        for item in payload["models"]:
            if not isinstance(item, dict):
                raise ValueError("Invalid model entry")
            name = item.get("name", item.get("model"))
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Invalid model name")
            names.add(model_key(name))
        if model_key(model) in names:
            return ComponentStatus(status="available", reason="chat_model_present")
        return ComponentStatus(status="missing", reason="chat_model_missing")
    except (httpx.ConnectError, httpx.TimeoutException, TimeoutError):
        return ComponentStatus(status="unreachable", reason="ollama_unreachable")
    except httpx.InvalidURL:
        return ComponentStatus(status="error", reason="ollama_endpoint_invalid")
    except (httpx.HTTPError, ValueError):
        return ComponentStatus(status="error", reason="ollama_response_invalid")


def combine_status(chat_model: ComponentStatus, stt: ComponentStatus, tts: ComponentStatus) -> SetupStatus:
    if chat_model.status in {"error", "unknown"}:
        state = "error"
    elif chat_model.status != "available":
        state = "needs_setup"
    elif stt.status != "available" or tts.status != "available":
        state = "degraded"
    else:
        state = "ready"
    return SetupStatus(state=state, chat_model=chat_model, stt=stt, tts=tts)


async def inspect_setup(settings: dict[str, Any], default_whisper_model: Path) -> SetupStatus:
    # Match the model and native CLI that the STT runtime will actually use.
    stt = inspect_model_file(str(settings.get("whisper_model_path", "") or default_whisper_model))
    if stt.status == "available" and not find_whisper_binary(str(settings.get("whisper_binary", "auto"))):
        stt = ComponentStatus(status="missing", reason="whisper_cli_missing")
    if stt.status == "available" and not find_system_tool("ffmpeg"):
        stt = ComponentStatus(status="missing", reason="ffmpeg_missing")
    tts = ComponentStatus(status="unknown", reason="voice_unverified")
    if str(settings.get("tts_engine", "piper")).strip().lower() == "piper":
        asset = inspect_model_file(str(settings.get("tts_model_path", "")).strip())
        if asset.status != "available":
            tts = asset
    # Even existing Piper assets or system voices do not prove working audio.
    # No audio import, voice enumeration, subprocess, installation or model load.
    async with httpx.AsyncClient(timeout=3.0, follow_redirects=False, trust_env=False) as client:
        chat_model = await inspect_chat_model(settings, client)
    return combine_status(chat_model, stt, tts)
