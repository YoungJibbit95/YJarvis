"""Bounded, read-only inventory for the active Desktop Settings.

Use existing Ollama readiness semantics and only project-managed model folders
plus paths the user explicitly configured. Presence is not inference/playback.
"""
from __future__ import annotations

import importlib.util
import itertools
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from .native_tools import find_system_tool, find_whisper_binary
from .setup_components import existing_tool
from .setup_readiness import inspect_model_file, model_key


def _file_present(path: Path) -> bool:
    return inspect_model_file(path).status == "available"


def _model_path(raw: str, root: Path, *, explicitly_configured: bool) -> Path | None:
    if not raw:
        return None
    try:
        path = Path(raw).expanduser().resolve()
        if not explicitly_configured and not path.is_relative_to(root.resolve()):
            return None
        return path
    except (ValueError, OSError, RuntimeError):
        return None


def local_models(settings: dict[str, Any], runtime: Path, default_whisper: Path) -> dict[str, Any]:
    models_root = runtime / "models"
    installed_whisper: dict[str, dict[str, Any]] = {}
    installed_piper: dict[str, dict[str, Any]] = {}

    def include_whisper(file: Path, configured: bool) -> None:
        if not file.name.startswith("ggml-") or file.suffix != ".bin":
            return
        if _file_present(file):
            installed_whisper[str(file)] = {
                "name": file.stem.removeprefix("ggml-"),
                "path": str(file),
                "active": configured,
                "installed": True,
                "verified_inference": False,
            }

    whisper_dir = models_root
    try:
        if whisper_dir.is_dir():
            for item in itertools.islice(whisper_dir.iterdir(), 100):
                file = _model_path(str(item), models_root, explicitly_configured=False)
                if file and file.is_file():
                    include_whisper(file, False)
    except OSError:
        pass

    active_whisper = str(settings.get("whisper_model_path", "") or default_whisper)
    wh_path = _model_path(active_whisper, models_root, explicitly_configured=True)
    if wh_path:
        include_whisper(wh_path, True)
    for entry in installed_whisper.values():
        entry["active"] = entry["path"] == str(wh_path)

    def include_piper(path: Path, configured: bool) -> None:
        if path.suffix != ".onnx" or not _file_present(path):
            return
        config = Path(str(path) + ".json")
        if not _file_present(config):
            return
        installed_piper[str(path)] = {
            "name": path.stem,
            "path": str(path),
            "active": configured,
            "installed": True,
            "paired_config": True,
            "verified_playback": False,
        }

    piper_root = models_root / "piper"
    try:
        if piper_root.is_dir():
            for directory in itertools.islice(piper_root.iterdir(), 100):
                resolved = _model_path(str(directory), piper_root, explicitly_configured=False)
                if not resolved or not resolved.is_dir():
                    continue
                for file in itertools.islice(resolved.iterdir(), 8):
                    model = _model_path(str(file), piper_root, explicitly_configured=False)
                    if model:
                        include_piper(model, False)
    except OSError:
        pass

    active_piper = _model_path(str(settings.get("tts_model_path", "")).strip(), piper_root, explicitly_configured=True)
    if active_piper:
        include_piper(active_piper, True)
    for entry in installed_piper.values():
        entry["active"] = entry["path"] == str(active_piper)

    whisper_binary = find_whisper_binary(str(settings.get("whisper_binary", "auto")))
    if not whisper_binary:
        whisper_binary = existing_tool("whisper-cli", runtime)
    ffmpeg = existing_tool("ffmpeg", runtime)
    say_supported = sys.platform == "darwin" and bool(find_system_tool("say"))
    piper_available = importlib.util.find_spec("piper") is not None or bool(find_system_tool("piper"))
    return {
        "whisper": {
            "models": list(installed_whisper.values()),
            "binary_available": bool(whisper_binary),
            "ffmpeg_available": bool(ffmpeg),
            "active_path": active_whisper,
            "note": "Dateiprüfung ist keine erfolgreiche Transkription.",
        },
        "tts": {
            "piper_voices": list(installed_piper.values()),
            "piper_runtime_available": piper_available,
            "say_supported": say_supported,
            "active_engine": str(settings.get("tts_engine", "piper")),
            "active_path": str(settings.get("tts_model_path", "")),
            "note": "Dateipaar ist keine erfolgreiche Audioausgabe.",
        },
    }


async def ollama_models(settings: dict[str, Any], client: httpx.AsyncClient) -> dict[str, Any]:
    base = str(settings.get("ollama_base_url", "http://127.0.0.1:11434")).rstrip("/")
    configured = str(settings.get("model_name", "")).strip()
    base_result: dict[str, Any] = {
        "status": "error", "models": [], "active_model": configured,
        "error": "Ollama-Inventar nicht verfügbar.",
    }
    try:
        parsed = urlsplit(base)
        _ = parsed.port
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or (
            parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
        ):
            raise ValueError("Invalid URL")
        response = await client.get(base + "/api/tags", timeout=4.0)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list) or len(payload["models"]) > 500:
            raise ValueError("Invalid list")
        models: list[dict[str, Any]] = []
        for item in payload["models"]:
            if not isinstance(item, dict):
                raise ValueError("Invalid model")
            name = item.get("name", item.get("model"))
            if not isinstance(name, str) or not 1 <= len(name) <= 160:
                raise ValueError("Invalid model tag")
            size = item.get("size")
            if size is not None and (type(size) is not int or size < 0):
                raise ValueError("Invalid model size")
            digest = item.get("digest", "")
            if not isinstance(digest, str) or len(digest) > 256:
                raise ValueError("Invalid model digest")
            models.append({
                "name": name, "digest": digest, "size_bytes": size,
                "active": model_key(name) == model_key(configured),
                "installed": True, "verified_inference": False,
            })
        return {"status": "online", "models": models, "active_model": configured, "error": None}
    except (httpx.ConnectError, httpx.TimeoutException):
        base_result.update(status="offline", error="Ollama nicht erreichbar. Verbindung prüfen und erneut laden.")
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        base_result["error"] = "Ollama-Modellinventar konnte nicht zuverlässig gelesen werden."
    return base_result


async def inspect_model_inventory(
    settings: dict[str, Any], runtime: Path, default_whisper: Path,
    *, client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    local = local_models(settings, runtime, default_whisper)
    if client is not None:
        ollama = await ollama_models(settings, client)
    else:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False) as remote:
            ollama = await ollama_models(settings, remote)
    return {"ollama": ollama, **local}
