"""One explicit, cancellable setup job; settings commit only after verification."""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .setup_components import install_tool, install_voice, install_whisper, restore_tools, existing_tool


class InstallSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat_model: str | None = Field(default=None, max_length=160)
    whisper_model: str | None = None
    voice: str | None = Field(default=None, max_length=100)
    install_ollama: bool = False

    @field_validator("chat_model")
    @classmethod
    def model_tag(cls, value):
        if value is not None and not re.fullmatch(r"(?:[A-Za-z0-9][A-Za-z0-9_.-]*/)*[A-Za-z0-9][A-Za-z0-9_.-]*(?::[A-Za-z0-9][A-Za-z0-9_.-]*)?", value):
            raise ValueError("Bitte einen gültigen Ollama-Modellnamen eingeben")
        return value


def local_endpoint(settings: dict) -> str:
    value = str(settings.get("ollama_base_url", "http://127.0.0.1:11434")).rstrip("/")
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("Einrichtung benötigt einen lokalen Ollama-Endpunkt in den Einstellungen")
    _ = parsed.port
    return value


class SetupInstaller:
    def __init__(self, runtime: Path, read_settings, write_settings):
        self.runtime = runtime
        self.read_settings = read_settings
        self.write_settings = write_settings
        self.task: asyncio.Task | None = None
        self.ollama: asyncio.subprocess.Process | None = None
        self.state = {"status": "idle", "id": None, "stage": "", "completed": 0, "total": None, "error": None, "configured_fields": [], "cancellable": False}
        self.journal = runtime / "setup" / "installation.json"
        self.voice_certificate_file = runtime / "setup" / "voice-verification.json"
        self.voice_certificate = None
        try:
            if self.voice_certificate_file.stat().st_size < 4096:
                value = json.loads(self.voice_certificate_file.read_text("utf-8"))
                if isinstance(value, dict):
                    self.voice_certificate = value
        except (OSError, ValueError):
            pass
        restore_tools(runtime)
        if self.journal.exists():
            try:
                loaded = json.loads(self.journal.read_text("utf-8"))
                if not isinstance(loaded, dict) or loaded.get("status") not in {"idle", "running", "completed", "failed", "cancelled", "interrupted"}:
                    raise ValueError("Invalid setup journal")
                self.state.update({key: loaded[key] for key in self.state if key in loaded})
                if self.state["status"] == "running":
                    self.state.update(status="interrupted", cancellable=False, error="Einrichtung wurde unterbrochen. Bitte erneut starten.")
            except (ValueError, KeyError, OSError):
                pass

    def persist(self):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        temp = self.journal.with_suffix(".tmp")
        temp.write_text(json.dumps(self.state), "utf-8")
        os.replace(temp, self.journal)

    def progress(self, completed: int, total: int | None):
        self.state.update(completed=completed, total=total)

    def voice_verified(self, settings: dict) -> bool:
        if not self.voice_certificate or settings.get("tts_engine") != "piper":
            return False
        try:
            file = Path(settings["tts_model_path"]).resolve()
            info = file.stat()
            return self.voice_certificate == {"path": str(file), "size": info.st_size, "mtime_ns": info.st_mtime_ns}
        except (OSError, ValueError, KeyError):
            return False

    def start(self, selection: InstallSelection):
        if self.task and not self.task.done():
            raise ValueError("Eine Einrichtung läuft bereits")
        if not any((selection.chat_model, selection.whisper_model, selection.voice, selection.install_ollama)):
            raise ValueError("Bitte mindestens eine Komponente auswählen")
        self.state = {"status": "running", "id": uuid4().hex, "stage": "Vorbereitung", "completed": 0, "total": None, "error": None, "configured_fields": [], "cancellable": True}
        self.persist()
        self.task = asyncio.create_task(self.run(selection))
        return dict(self.state)

    async def cancel(self):
        if self.task and not self.task.done() and self.state["cancellable"]:
            self.task.cancel()
        return dict(self.state)

    async def ensure_ollama(self, client, settings, install: bool = False):
        base = local_endpoint(settings)
        try:
            response = await client.get(base + "/api/tags", timeout=2)
            if response.status_code == 200:
                return base
        except httpx.HTTPError:
            pass
        binary = existing_tool("ollama", self.runtime)
        if not binary and install:
            self.state["stage"] = "Ollama herunterladen und entpacken"
            binary = await install_tool(client, self.runtime, "ollama", self.progress)
        if not binary:
            raise ValueError("Ollama fehlt. Bitte die Ollama-Installation auswählen.")
        if self.ollama and self.ollama.returncode is None:
            pass
        else:
            self.ollama = await asyncio.create_subprocess_exec(binary, "serve", env={**os.environ, "OLLAMA_HOST": base},
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {"start_new_session": True}))
        for _ in range(120):
            if self.ollama.returncode is not None:
                raise ValueError("Ollama konnte nicht gestartet werden")
            try:
                if (await client.get(base + "/api/tags", timeout=2)).status_code == 200:
                    return base
            except httpx.HTTPError:
                pass
            await asyncio.sleep(.5)
        raise ValueError("Ollama wird nicht bereit; bitte Server/Port prüfen")

    async def pull(self, client, base, model):
        async with client.stream("POST", base + "/api/pull", json={"model": model, "stream": True}, timeout=httpx.Timeout(120, connect=10)) as response:
            response.raise_for_status()
            success = False
            async for line in response.aiter_lines():
                if not line:
                    continue
                if len(line) > 100_000:
                    raise ValueError("Ungültige Ollama-Fortschrittsdaten")
                item = json.loads(line)
                if item.get("error"):
                    raise ValueError(str(item["error"])[:300])
                status = str(item.get("status", ""))
                self.state["stage"] = ("Chat-Modellinformationen laden" if "manifest" in status and status.startswith("pulling")
                    else "Chat-Modell herunterladen" if status.startswith("pulling")
                    else "Chat-Modell prüfen" if status.startswith("verifying")
                    else "Chat-Modell speichern" if status.startswith("writing")
                    else "Chat-Modellinstallation abschließen")
                self.progress(int(item.get("completed", 0)), item.get("total"))
                success = item.get("status") == "success"
            if not success:
                raise ValueError("Ollama-Download hat keinen erfolgreichen Abschluss gemeldet")
        info = await client.post(base + "/api/show", json={"model": model}, timeout=20)
        info.raise_for_status()
        capabilities = info.json().get("capabilities")
        if info.json().get("remote_model") or info.json().get("remote_host"):
            raise ValueError("Bitte ein lokal ausführbares Ollama-Modell auswählen")
        if capabilities is not None and "completion" not in capabilities:
            raise ValueError("Dieses Modell unterstützt keinen Chat/Textabschluss")
        # Verify real inference before activating a model (not just inventory).
        self.state["stage"] = "Chat-Modell auf diesem Rechner testen"
        self.progress(0, None)
        test = await client.post(base + "/api/generate", json={"model": model, "prompt": "Antworte kurz mit OK.", "stream": False, "options": {"num_predict": 16}}, timeout=180)
        test.raise_for_status()
        output = test.json().get("response") or test.json().get("thinking")
        if not isinstance(output, str) or not output.strip():
            raise ValueError("Das Modell liefert keine Textantwort")

    async def run(self, selection):
        try:
            before = await self.read_settings()
            update = {}
            async with httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client:
                if selection.install_ollama or selection.chat_model:
                    self.state["stage"] = "Ollama prüfen"
                    base = await self.ensure_ollama(client, before, install=True)
                    if selection.chat_model:
                        await self.pull(client, base, selection.chat_model)
                        update["model_name"] = selection.chat_model
                if selection.whisper_model:
                    self.state["stage"] = "Spracheingabe: Programme und Modell installieren"
                    self.progress(0, None)
                    update.update(await install_whisper(client, self.runtime, selection.whisper_model, self.progress))
                if selection.voice:
                    self.state["stage"] = "Stimme und Konfiguration installieren"
                    self.progress(0, None)
                    update.update(await install_voice(client, self.runtime, selection.voice, self.progress))
            current = await self.read_settings()
            if any(current.get(key) != before.get(key) for key in update):
                raise ValueError("Einstellungen wurden inzwischen geändert. Bitte Einrichtung erneut starten.")
            if update:
                self.state.update(stage="Einstellungen speichern", cancellable=False)
                commit = asyncio.create_task(self.write_settings(update, before))
                try:
                    await asyncio.shield(commit)
                except asyncio.CancelledError:
                    await commit  # A settings commit cannot be half-cancelled.
            if selection.voice:
                file = Path(update["tts_model_path"]).resolve()
                info = file.stat()
                self.voice_certificate = {"path": str(file), "size": info.st_size, "mtime_ns": info.st_mtime_ns}
                temp = self.voice_certificate_file.with_suffix(".tmp")
                temp.write_text(json.dumps(self.voice_certificate), "utf-8")
                os.replace(temp, self.voice_certificate_file)
            self.state.update(status="completed", stage="Installiert, geprüft und vorkonfiguriert", error=None, configured_fields=list(update))
        except asyncio.CancelledError:
            self.state.update(status="cancelled", stage="Abgebrochen", error=None)
        except Exception as error:
            # Never expose HTTP signed redirect URLs, tokens or raw tracebacks.
            detail = str(error) if isinstance(error, ValueError) else "Einrichtung fehlgeschlagen. Bitte Verbindung, Speicherplatz und gewählte Komponente prüfen."
            self.state.update(status="failed", error=detail[:400])
        finally:
            self.state["cancellable"] = False
            self.persist()

    async def startup(self):
        if existing_tool("ollama", self.runtime) and (self.runtime / "setup" / "tools.json").exists():
            try:
                async with httpx.AsyncClient(trust_env=False) as client:
                    await self.ensure_ollama(client, await self.read_settings())
            except (ValueError, httpx.HTTPError):
                pass  # Setup stays accessible when a previously installed server fails.

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await self.task
        if self.ollama and self.ollama.returncode is None:
            if sys.platform == "win32":
                killer = await asyncio.create_subprocess_exec("taskkill.exe", "/PID", str(self.ollama.pid), "/T", "/F", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                await killer.wait()
            else:
                import signal
                try:
                    os.killpg(self.ollama.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            await asyncio.wait_for(self.ollama.wait(), timeout=10)
