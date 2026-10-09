"""YJVOICE-01 process ownership, FFmpeg/Whisper failures, formats and cleanup."""
import asyncio
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from jarvis_agent import audio
from jarvis_agent.config import AppConfig


def _config(tmp_path: Path) -> AppConfig:
    runtime = tmp_path / "runtime"
    for folder in (runtime / "audio", runtime / "tts", runtime / "models"):
        folder.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        project_root=tmp_path, runtime_dir=runtime, db_path=runtime / "test.db",
        audio_tmp_dir=runtime / "audio", tts_tmp_dir=runtime / "tts",
        default_whisper_model=runtime / "models" / "whisper.bin",
        profile_path=runtime / "profile.json", host="127.0.0.1", port=8787,
    )


def _settings(config: AppConfig) -> dict[str, str]:
    config.default_whisper_model.write_bytes(b"test-model")
    return {"whisper_binary": "fixture-whisper", "whisper_model_path": str(config.default_whisper_model),
            "language": "de"}


def test_stt_subprocess_success_and_nonzero_stderr():
    async def exercise():
        ok = await audio._run_stt_subprocess(
            [sys.executable, "-c", "print('ok')"], timeout_seconds=6, phase="fixture")
        assert ok.returncode == 0 and ok.stdout.strip() == "ok"
        failed = await audio._run_stt_subprocess(
            [sys.executable, "-c", "import sys; print('failure', file=sys.stderr); sys.exit(9)"],
            timeout_seconds=6, phase="fixture")
        assert failed.returncode == 9 and "failure" in failed.stderr
    asyncio.run(exercise())


def test_real_hanging_stt_child_is_killed_without_leaking_timeout():
    start = time.monotonic()
    with pytest.raises(audio.AudioError, match="Zeitlimit"):
        asyncio.run(audio._run_stt_subprocess(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout_seconds=0.2, phase="Whisper-Inferenz"))
    assert time.monotonic() - start < 6


def test_missing_stt_executable_yields_audio_error():
    with pytest.raises(audio.AudioError, match="nicht gestartet"):
        asyncio.run(audio._run_stt_subprocess(
            ["definitely-missing-yjarvis-whisper-exe", "--help"],
            timeout_seconds=1, phase="Whisper-Inferenz"))


@pytest.mark.parametrize("ext", [".webm", ".mp4"])
def test_ffmpeg_conversion_whisper_result_and_temp_cleanup(ext, tmp_path, monkeypatch):
    config = _config(tmp_path)
    settings = _settings(config)
    monkeypatch.setattr(audio, "_find_whisper_binary", lambda *_: "fixture-whisper")
    monkeypatch.setattr(audio, "_find_ffmpeg_binary", lambda: "fixture-ffmpeg")
    calls = []

    async def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "fixture-ffmpeg":
            Path(args[-1]).write_bytes(b"fake-16k-wave")
        else:
            prefix = Path(args[args.index("-of") + 1])
            prefix.with_suffix(".txt").write_text("Jarvis, öffne Spotify", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(audio, "_run_stt_subprocess", fake_run)
    source = tmp_path / ("utterance" + ext)
    source.write_bytes(b"fixture-media")
    result = asyncio.run(audio.transcribe_with_whisper_cpp(
        source_path=source, settings=settings, config=config))
    assert result[0].lower().startswith("jarvis")
    assert len(calls) == 2
    assert calls[0][0][0] == "fixture-ffmpeg"
    assert "-nostdin" in calls[0][0]
    assert calls[0][1]["timeout_seconds"] == audio.STT_FFMPEG_TIMEOUT_SECONDS
    assert calls[1][1]["timeout_seconds"] == audio.STT_WHISPER_TIMEOUT_SECONDS
    assert list(config.audio_tmp_dir.iterdir()) == []


@pytest.mark.parametrize("stage", ["convert", "whisper", "empty", "convert-timeout", "whisper-timeout"])
def test_failures_empty_audio_and_timeout_always_cleanup(stage, tmp_path, monkeypatch):
    config = _config(tmp_path)
    settings = _settings(config)
    source = tmp_path / "input.mp4"
    source.write_bytes(b"fixture-media")
    monkeypatch.setattr(audio, "_find_whisper_binary", lambda *_: "fixture-whisper")
    monkeypatch.setattr(audio, "_find_ffmpeg_binary", lambda: "fixture-ffmpeg")

    async def run(args, **kwargs):
        is_convert = args[0] == "fixture-ffmpeg"
        if (stage == "convert-timeout" and is_convert) or (stage == "whisper-timeout" and not is_convert):
            raise audio.AudioError("Zeitlimit überschritten")
        if (stage == "convert" and is_convert) or (stage == "whisper" and not is_convert):
            return subprocess.CompletedProcess(args, 7, "", "native execution failed")
        if is_convert:
            Path(args[-1]).write_bytes(b"converted")
        elif stage != "empty":
            Path(args[args.index("-of") + 1] + ".txt").write_text("Jarvis", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(audio, "_run_stt_subprocess", run)
    if stage == "empty":
        result = asyncio.run(audio.transcribe_with_whisper_cpp(
            source_path=source, settings=settings, config=config))
        assert result[0] == ""
    else:
        with pytest.raises(audio.AudioError):
            asyncio.run(audio.transcribe_with_whisper_cpp(
                source_path=source, settings=settings, config=config))
    assert list(config.audio_tmp_dir.iterdir()) == []


def test_missing_binary_model_ffmpeg_are_specific(tmp_path, monkeypatch):
    config = _config(tmp_path)
    source = tmp_path / "input.mp4"
    source.write_bytes(b"fixture")
    settings = _settings(config)
    monkeypatch.setattr(audio, "_find_whisper_binary", lambda *_: None)
    with pytest.raises(audio.AudioError, match="Whisper Binary"):
        asyncio.run(audio.transcribe_with_whisper_cpp(source_path=source, settings=settings, config=config))
    monkeypatch.setattr(audio, "_find_whisper_binary", lambda *_: "fixture-whisper")
    settings["whisper_model_path"] = str(tmp_path / "missing.ggml")
    with pytest.raises(audio.AudioError, match="Whisper Modell fehlt"):
        asyncio.run(audio.transcribe_with_whisper_cpp(source_path=source, settings=settings, config=config))
    settings["whisper_model_path"] = str(config.default_whisper_model)
    monkeypatch.setattr(audio, "_find_ffmpeg_binary", lambda: None)
    with pytest.raises(audio.AudioError, match="ffmpeg fehlt") as caught:
        asyncio.run(audio.transcribe_with_whisper_cpp(source_path=source, settings=settings, config=config))
    assert "brew install" not in str(caught.value)
    assert list(config.audio_tmp_dir.iterdir()) == []


def test_wav_skips_ffmpeg_and_reaches_whisper(tmp_path, monkeypatch):
    config = _config(tmp_path)
    settings = _settings(config)
    source = tmp_path / "input.wav"
    source.write_bytes(b"valid-test-wave")
    monkeypatch.setattr(audio, "_find_whisper_binary", lambda *_: "fixture-whisper")
    monkeypatch.setattr(audio, "_find_ffmpeg_binary", lambda: None)
    async def run(args, **kwargs):
        Path(args[args.index("-of") + 1] + ".txt").write_text("Jarvis, wie geht es?", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(audio, "_run_stt_subprocess", run)
    text, _, _ = asyncio.run(audio.transcribe_with_whisper_cpp(source_path=source, settings=settings, config=config))
    assert "Jarvis" in text
    assert list(config.audio_tmp_dir.iterdir()) == []


def test_http_stt_failure_returns_503_and_removes_upload(tmp_path, monkeypatch):
    import jarvis_agent.main as main_module

    config = _config(tmp_path)
    async def settings():
        return _settings(config)
    async def fail_stt(**kwargs):
        raise audio.AudioError("Whisper-Inferenz: Zeitlimit überschritten")
    monkeypatch.setattr(main_module, "config", config)
    monkeypatch.setattr(main_module.database, "get_settings", settings)
    monkeypatch.setattr(main_module, "transcribe_with_whisper_cpp", fail_stt)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app),
                                     base_url="http://agent") as client:
            response = await client.post("/v1/audio/transcribe",
                                         files={"file": ("recording.mp4", b"fixture-audio", "audio/mp4")})
            assert response.status_code == 503
            assert "Zeitlimit" in response.json()["detail"]
    asyncio.run(exercise())
    assert list(config.audio_tmp_dir.iterdir()) == []
