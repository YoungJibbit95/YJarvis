import asyncio
import hashlib
import json
import zipfile
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from jarvis_agent.setup_downloads import download, extract_archive, source_url
from jarvis_agent.setup_installation import InstallSelection, SetupInstaller, local_endpoint
from jarvis_agent.setup_install_api import create_install_router


@pytest.mark.parametrize("tag", ["../model", "https://evil/model", "-exec", "name;cmd", "name\nnext", "a//b"])
def test_model_tags_cannot_be_urls_or_commands(tag):
    with pytest.raises(ValueError):
        InstallSelection(chat_model=tag)


@pytest.mark.parametrize("url", ["http://github.com/file", "https://github.com.evil/file", "https://user:pass@github.com/file", "https://127.0.0.1/file"])
def test_download_sources_reject_untrusted_targets(url):
    with pytest.raises(ValueError):
        source_url(url)


def test_local_install_cannot_target_an_external_ollama():
    for endpoint in ["https://127.0.0.1", "http://remote:11434", "http://127.0.0.1/proxy", "http://user:pass@localhost"]:
        with pytest.raises(ValueError):
            local_endpoint({"ollama_base_url": endpoint})
    assert local_endpoint({"ollama_base_url": "http://127.0.0.1:11434"}) == "http://127.0.0.1:11434"


def test_hash_failure_preserves_previous_file_and_removes_partial(tmp_path):
    async def run():
        target = tmp_path / "model.bin"
        target.write_bytes(b"previous")
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"bad"))) as client:
            with pytest.raises(ValueError, match="SHA256"):
                await download(client, "https://huggingface.co/file", target, "0" * 64, 3, lambda *_: None)
        assert target.read_bytes() == b"previous"
        assert not target.with_name("model.bin.part").exists()
    asyncio.run(run())


def test_successful_download_is_atomic_and_cache_is_verified(tmp_path):
    async def run():
        target = tmp_path / "asset.bin"
        data = b"verified"
        sha = hashlib.sha256(data).hexdigest()
        calls = []
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: (calls.append(request) or httpx.Response(200, content=data)))) as client:
            await download(client, "https://huggingface.co/asset", target, sha, len(data), lambda *_: None)
            await download(client, "https://huggingface.co/asset", target, sha, len(data), lambda *_: None)
        assert len(calls) == 1
        assert target.read_bytes() == data
    asyncio.run(run())


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/drive", "a\\..\\..\\escape"])
def test_archive_preflight_writes_nothing_for_unsafe_member(tmp_path, name):
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("safe.txt", "safe")
        package.writestr(name, "escape")
    destination = tmp_path / "install"
    with pytest.raises(ValueError):
        extract_archive(archive, destination)
    assert list(destination.iterdir()) == []


def test_archive_rejects_links_before_extraction(tmp_path):
    archive = tmp_path / "links.zip"
    link = zipfile.ZipInfo("link")
    link.create_system = 3
    link.external_attr = (0o120777 << 16)
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr(link, "../outside")
    with pytest.raises(ValueError):
        extract_archive(archive, tmp_path / "destination")


def test_redirect_cannot_escape_source_allowlist(tmp_path):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(302, headers={"location": "https://evil.example/file"}))) as client:
            with pytest.raises(ValueError, match="Downloadquelle"):
                await download(client, "https://github.com/file", tmp_path / "asset", "0" * 64, 1, lambda *_: None)
        assert not (tmp_path / "asset").exists()
    asyncio.run(run())


def test_cancelled_transfer_removes_partial_and_preserves_previous_file(tmp_path):
    async def run():
        started = asyncio.Event()
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"ab"
                started.set()
                await asyncio.sleep(100)
        target = tmp_path / "asset"
        target.write_bytes(b"previous")
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Stream()))) as client:
            task = asyncio.create_task(download(client, "https://huggingface.co/file", target, "0" * 64, 5, lambda *_: None))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert target.read_bytes() == b"previous"
        assert not (tmp_path / "asset.part").exists()
    asyncio.run(run())


def test_pcm_playback_uses_actual_samples_and_blocks_until_output_finishes(tmp_path, monkeypatch):
    import wave
    from jarvis_agent import audio_playback
    file = tmp_path / "probe.wav"
    with wave.open(str(file), "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 100)
    calls = []
    monkeypatch.setattr(audio_playback.sounddevice, "play", lambda samples, rate, **kwargs: calls.append((len(samples), rate, kwargs)))
    audio_playback.play_wav(file)
    assert calls == [(100, 16000, {"blocking": True})]


def manager(tmp_path, settings=None):
    current = dict(settings or {"model_name": "old", "language": "de", "ollama_base_url": "http://127.0.0.1:11434"})
    writes = []
    async def read():
        return dict(current)
    async def write(update, expected=None):
        writes.append(update)
        current.update(update)
    return SetupInstaller(tmp_path, read, write), current, writes


def test_failure_does_not_activate_model(tmp_path):
    async def run():
        installer, current, writes = manager(tmp_path)
        async def ready(*_, **__): return "http://127.0.0.1:11434"
        async def failure(*_): raise ValueError("model missing")
        installer.ensure_ollama = ready
        installer.pull = failure
        installer.start(InstallSelection(chat_model="new"))
        await installer.task
        assert installer.state["status"] == "failed"
        assert current["model_name"] == "old" and writes == []
    asyncio.run(run())


def test_reasoning_model_can_verify_inference_with_thinking_tokens(tmp_path):
    async def run():
        installer, _, _ = manager(tmp_path)
        def response(request):
            if request.url.path == "/api/pull":
                return httpx.Response(200, content=b'{"status":"success"}\n')
            if request.url.path == "/api/show":
                return httpx.Response(200, json={"capabilities": ["completion", "thinking"]})
            return httpx.Response(200, json={"response": "", "thinking": "Thinking before the final answer"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            await installer.pull(client, "http://127.0.0.1:11434", "reasoning-model")
    asyncio.run(run())


def test_database_configuration_rejects_stale_snapshot_atomically(tmp_path):
    from jarvis_agent.db import Database
    async def run():
        db = Database(db_path=tmp_path / "db.sqlite", project_root=tmp_path, default_whisper_model=tmp_path / "model.bin")
        await db.init()
        before = await db.get_settings()
        await db.update_settings({"model_name": "user-selected"})
        with pytest.raises(ValueError, match="inzwischen"):
            await db.update_settings_if_current({"model_name": "downloaded", "tts_voice": "new"}, before)
        current = await db.get_settings()
        assert current["model_name"] == "user-selected"
        assert current["tts_voice"] == before["tts_voice"]
        await db.update_settings_if_current({"model_name": "downloaded"}, current)
        assert (await db.get_settings())["model_name"] == "downloaded"
    asyncio.run(run())


def test_configuration_commits_only_selected_keys_and_rejects_concurrent_changes(tmp_path):
    async def run():
        installer, current, writes = manager(tmp_path)
        async def ready(*_, **__): return "http://127.0.0.1:11434"
        async def pull(*_): pass
        installer.ensure_ollama = ready
        installer.pull = pull
        installer.start(InstallSelection(chat_model="new"))
        await installer.task
        assert writes == [{"model_name": "new"}] and current["language"] == "de"
        assert installer.state["status"] == "completed"
        async def concurrent(*_): current["model_name"] = "user-change"
        installer.pull = concurrent
        installer.start(InstallSelection(chat_model="another"))
        await installer.task
        assert installer.state["status"] == "failed"
        assert current["model_name"] == "user-change"
    asyncio.run(run())


def test_single_active_job_and_cancellation(tmp_path):
    async def run():
        installer, _, writes = manager(tmp_path)
        started = asyncio.Event()
        async def waiting(*_, **__):
            started.set()
            await asyncio.sleep(100)
        installer.ensure_ollama = waiting
        installer.start(InstallSelection(install_ollama=True))
        await started.wait()
        with pytest.raises(ValueError, match="bereits"):
            installer.start(InstallSelection(install_ollama=True))
        await installer.cancel()
        await installer.task
        assert installer.state["status"] == "cancelled" and writes == []
    asyncio.run(run())


def test_restart_marks_running_job_interrupted_without_restarting(tmp_path):
    folder = tmp_path / "setup"
    folder.mkdir()
    (folder / "installation.json").write_text(json.dumps({"status": "running"}), "utf-8")
    installer, _, _ = manager(tmp_path)
    assert installer.state["status"] == "interrupted"
    assert installer.task is None


def test_voice_evidence_requires_matching_asset_and_engine(tmp_path):
    installer, _, _ = manager(tmp_path)
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    settings = {"tts_engine": "piper", "tts_model_path": str(model)}
    assert not installer.voice_verified(settings)
    stat = model.stat()
    installer.voice_certificate = {"path": str(model.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    assert installer.voice_verified(settings)
    assert not installer.voice_verified({**settings, "tts_engine": "say"})
    model.write_bytes(b"replaced-model")
    assert not installer.voice_verified(settings)


def test_installation_requires_explicit_trusted_browser_origin(tmp_path):
    async def run():
        installer, _, _ = manager(tmp_path)
        app = FastAPI()
        app.include_router(create_install_router(installer))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for origin in [None, "null", "https://evil.example"]:
                headers = {"origin": origin} if origin else {}
                assert (await client.post("/v1/setup/install", json={"install_ollama": True}, headers=headers)).status_code == 403
                assert (await client.delete("/v1/setup/install", headers=headers)).status_code == 403
            assert installer.task is None
    asyncio.run(run())
