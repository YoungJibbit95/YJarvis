"""Official component recipes for guided setup; no arbitrary executable/URL input."""
from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import wave
from pathlib import Path
from uuid import uuid4

import httpx

from .setup_downloads import download, extract_archive, repository_file, source_json
from .native_tools import find_system_tool, find_whisper_binary


WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3", "large-v3-turbo")
VOICE_REPO = "rhasspy/piper-voices"
VOICE_KEY = re.compile(r"[a-z]{2,3}_[A-Z]{2}-[a-zA-Z0-9_]+-(?:x_low|low|medium|high)")


async def voices(client: httpx.AsyncClient) -> dict:
    catalog = await source_json(client, f"https://huggingface.co/{VOICE_REPO}/resolve/main/voices.json")
    if not isinstance(catalog, dict) or len(catalog) > 5000:
        raise ValueError("Ungültiger Stimmenkatalog")
    return {key: value for key, value in catalog.items() if VOICE_KEY.fullmatch(key)}


async def install_voice(client, runtime: Path, key: str, progress) -> dict:
    if not VOICE_KEY.fullmatch(key):
        raise ValueError("Ungültige Piper-Stimme")
    entry = (await voices(client)).get(key)
    if not entry:
        raise ValueError("Stimme nicht im offiziellen Piper-Katalog")
    names = list(entry["files"])
    model = next((name for name in names if name.endswith(f"/{key}.onnx")), None)
    if not model or model + ".json" not in names:
        raise ValueError("Stimme hat kein vollständiges Modell/Config-Paar")
    if any(part in {"", ".", ".."} for part in model.split("/")) or not re.fullmatch(r"[a-zA-Z0-9_/.-]+", model):
        raise ValueError("Ungültiger Modellpfad")
    folder = runtime / "models" / "piper" / key
    target = await repository_file(client, VOICE_REPO, model, folder / f"{key}.onnx", progress)
    await repository_file(client, VOICE_REPO, model + ".json", folder / f"{key}.onnx.json", progress)
    card = str(Path(model).parent).replace("\\", "/") + "/MODEL_CARD"
    if card in names:
        await repository_file(client, VOICE_REPO, card, folder / "MODEL_CARD", progress)
    from piper import PiperVoice
    # Model parsing succeeds before its settings become active. No playback on install.
    def verify_voice():
        voice = PiperVoice.load(str(target))
        probe = folder / f"verification-{uuid4().hex}.wav"
        try:
            with wave.open(str(probe), "wb") as wav:
                voice.synthesize_wav("Hallo, Jarvis ist bereit.", wav)
            with wave.open(str(probe), "rb") as wav:
                if wav.getnframes() == 0:
                    raise ValueError("Die Stimme erzeugt keine Audiodaten")
            try:
                if sys.platform == "darwin":
                    subprocess.run(["afplay", str(probe)], check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    from .audio_playback import play_wav
                    play_wav(probe)
            except Exception as error:
                raise ValueError("Stimme konnte nicht ausgegeben werden. Bitte ein funktionierendes Audio-Ausgabegerät auswählen und erneut versuchen.") from error
        finally:
            probe.unlink(missing_ok=True)
    verification = asyncio.create_task(asyncio.to_thread(verify_voice))
    try:
        await asyncio.shield(verification)
    except asyncio.CancelledError:
        await verification
        raise
    return {"tts_engine": "piper", "tts_model_path": str(target), "tts_voice": key}


def existing_tool(name: str, runtime: Path) -> str | None:
    command = find_whisper_binary() if name in {"whisper-cli", "whisper-cpp"} else find_system_tool(name)
    if command:
        return command
    if name == "ollama" and sys.platform == "win32":
        candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.is_file():
            return str(candidate)
    manifest = runtime / "setup" / "tools.json"
    if manifest.is_file():
        try:
            candidate = Path(json.loads(manifest.read_text("utf-8"))[name])
            if candidate.resolve().is_relative_to((runtime / "tools").resolve()) and candidate.is_file():
                return str(candidate)
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return None


def remember_tool(name: str, executable: Path, runtime: Path) -> None:
    manifest = runtime / "setup" / "tools.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(manifest.read_text("utf-8")) if manifest.exists() else {}
    data[name] = str(executable)
    temp = manifest.with_suffix(".tmp")
    temp.write_text(json.dumps(data), "utf-8")
    os.replace(temp, manifest)
    if name == "ffmpeg":
        os.environ["PATH"] = str(executable.parent) + os.pathsep + os.environ.get("PATH", "")


def restore_tools(runtime: Path) -> None:
    # Frozen Python already ships the redistributable DLLs. Native helper
    # processes need the same DLL directories on PATH, without a system installer.
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        bundle = Path(sys._MEIPASS)
        directories = {str(bundle), *(str(file.parent) for file in bundle.rglob("msvcp140.dll"))}
        os.environ["PATH"] = os.pathsep.join(sorted(directories)) + os.pathsep + os.environ.get("PATH", "")
    for name in ("ffmpeg", "whisper-cli"):
        command = existing_tool(name, runtime)
        if command:
            os.environ["PATH"] = str(Path(command).parent) + os.pathsep + os.environ.get("PATH", "")


async def _install_macos_tool(name: str, progress) -> str:
    formula = {"whisper-cli": "whisper.cpp", "ffmpeg": "ffmpeg"}.get(name)
    if not formula:
        raise ValueError(f"{name} kann auf macOS nicht automatisch installiert werden")
    brew = find_system_tool("brew")
    if not brew:
        raise ValueError("Homebrew fehlt. Bitte Homebrew installieren und danach die Whisper-Einrichtung erneut starten.")
    progress(0, None)
    process = await asyncio.create_subprocess_exec(
        brew, "install", formula,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=1800)
    except asyncio.TimeoutError as error:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        await process.wait()
        raise ValueError(f"Homebrew-Installation von {formula} hat das Zeitlimit überschritten") from error
    except asyncio.CancelledError:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        await process.wait()
        raise
    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip().splitlines()
        suffix = f": {detail[-1][:180]}" if detail else ""
        raise ValueError(f"Homebrew konnte {formula} nicht installieren{suffix}")
    executable = find_whisper_binary() if name == "whisper-cli" else find_system_tool(name)
    if not executable:
        raise ValueError(f"Homebrew meldet {formula} installiert, aber das Programm wurde nicht gefunden")
    return executable


async def install_tool(client, runtime: Path, name: str, progress) -> str:
    existing = existing_tool(name, runtime)
    if existing:
        if name == "ffmpeg":
            probe = await asyncio.create_subprocess_exec(existing, "-version", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}))
            try:
                if await asyncio.wait_for(probe.wait(), timeout=15) != 0:
                    raise ValueError("Vorhandenes FFmpeg ist nicht funktionsfähig")
            finally:
                if probe.returncode is None:
                    probe.kill(); await probe.wait()
        return existing
    if sys.platform == "darwin":
        return await _install_macos_tool(name, progress)
    if sys.platform != "win32":
        raise ValueError(f"{name} fehlt. Auf dieser Plattform bitte über den System-Paketmanager installieren.")
    recipes = {
        "ollama": ("ollama/ollama", "latest", "ollama-windows-amd64.zip", "ollama.exe"),
        "whisper-cli": ("ggml-org/whisper.cpp", "tags/v1.8.3", "whisper-bin-x64.zip", "whisper-cli.exe"),
        "ffmpeg": ("BtbN/FFmpeg-Builds", "latest", "ffmpeg-master-latest-win64-gpl.zip", "ffmpeg.exe"),
    }
    repo, release, filename, exe_name = recipes[name]
    info = await source_json(client, f"https://api.github.com/repos/{repo}/releases/{release}")
    asset = next((item for item in info["assets"] if item["name"] == filename), None)
    if not asset or not str(asset.get("digest", "")).startswith("sha256:"):
        raise ValueError(f"{name}: offizielle Release-Datei mit SHA256 fehlt")
    sha256 = asset["digest"].removeprefix("sha256:")
    archive = runtime / "setup" / "downloads" / f"{name}-{sha256[:16]}.zip"
    await download(client, asset["browser_download_url"], archive, sha256, asset["size"], progress)
    folder = runtime / "tools" / f"{name}-{sha256[:16]}"
    extraction = asyncio.create_task(asyncio.to_thread(extract_archive, archive, folder))
    try:
        await asyncio.shield(extraction)
    except asyncio.CancelledError:
        await extraction
        raise
    matches = list(folder.rglob(exe_name))
    if len(matches) != 1:
        raise ValueError(f"{name}: ausführbare Datei fehlt oder ist mehrdeutig")
    executable = matches[0].resolve()
    if not executable.is_relative_to(folder.resolve()):
        raise ValueError("Programm verlässt den Installationsordner")
    remember_tool(name, executable, runtime)
    return str(executable)


async def install_whisper(client, runtime: Path, model: str, progress) -> dict:
    if model not in WHISPER_MODELS:
        raise ValueError("Whisper-Modell wird nicht unterstützt")
    binary = await install_tool(client, runtime, "whisper-cli", progress)
    await install_tool(client, runtime, "ffmpeg", progress)
    file = f"ggml-{model}.bin"
    target = await repository_file(client, "ggerganov/whisper.cpp", file, runtime / "models" / file, progress)
    # Verify the actual native runtime and model loading with disposable silence.
    probe = runtime / "setup" / f"whisper-probe-{uuid4().hex}.wav"
    probe.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(probe), "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 16000)
    child = await asyncio.create_subprocess_exec(binary, "-m", str(target), "-f", str(probe), "-nt", "-l", "de",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}))
    try:
        if await asyncio.wait_for(child.wait(), timeout=180) != 0:
            raise ValueError("Whisper-Programm oder Modell konnte nicht geladen werden")
    finally:
        if child.returncode is None:
            child.kill(); await child.wait()
        probe.unlink(missing_ok=True)
    return {"whisper_binary": binary, "whisper_model_path": str(target)}
