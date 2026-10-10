"""YJUX-01 local inventory: read-only, bounded sources and truthful states."""
import asyncio
from pathlib import Path

import httpx
import pytest

from jarvis_agent import setup_inventory as inventory


def client(response):
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response))


def test_inventory_reports_actual_ollama_tags_and_exact_active_model(tmp_path):
    payload = {"models": [
        {"name": "qwen2.5:3b-instruct", "digest": "sha256:a", "size": 123456},
        {"name": "other:latest", "digest": "sha256:b", "size": 4422},
    ]}
    async def scenario():
        async with client(httpx.Response(200, json=payload)) as transport:
            result = await inventory.inspect_model_inventory({
                "ollama_base_url": "http://127.0.0.1:11434",
                "model_name": "qwen2.5:3b-instruct",
            }, tmp_path, tmp_path / "models" / "ggml-small.bin", client=transport)
        assert result["ollama"]["status"] == "online"
        assert [entry["active"] for entry in result["ollama"]["models"]] == [True, False]
        assert result["ollama"]["models"][0]["size_bytes"] == 123456
        assert result["ollama"]["models"][0]["verified_inference"] is False
        assert result["ollama"]["error"] is None
    asyncio.run(scenario())


@pytest.mark.parametrize("reply,status", [
    (httpx.Response(200, json={"models": [{"name": 123}]}), "error"),
    (httpx.Response(200, json={"models": [{"name": "valid", "size": "not-a-number"}]}), "error"),
    (httpx.Response(503), "error"),
])
def test_broken_ollama_data_is_not_misreported_as_installed(tmp_path, reply, status):
    async def scenario():
        async with client(reply) as transport:
            result = await inventory.ollama_models({
                "ollama_base_url": "http://127.0.0.1:11434",
                "model_name": "configured",
            }, transport)
        assert result["status"] == status
        assert result["models"] == []
    asyncio.run(scenario())


def test_offline_and_invalid_endpoints_never_mark_models_installed():
    def fail(request):
        raise httpx.ConnectError("offline", request=request)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as transport:
            state = await inventory.ollama_models({
                "ollama_base_url": "http://127.0.0.1:11434", "model_name": "missing",
            }, transport)
            assert state["status"] == "offline"
            assert state["models"] == []
            invalid = await inventory.ollama_models({
                "ollama_base_url": "file:///private/file", "model_name": "model",
            }, transport)
            assert invalid["status"] == "error"
            assert invalid["models"] == []
    asyncio.run(scenario())


def test_whisper_and_piper_only_read_managed_or_explicit_models(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    models = root / "models"
    models.mkdir(parents=True)
    available_whisper = models / "ggml-small.bin"
    available_whisper.write_bytes(b"model")
    (models / "ggml-base.bin").write_bytes(b"")
    foreign = tmp_path / "unmanaged" / "ggml-custom.bin"
    foreign.parent.mkdir()
    foreign.write_bytes(b"explicit")
    piper = models / "piper"
    complete = piper / "de_DE-sample-medium"
    complete.mkdir(parents=True)
    voice = complete / "de_DE-sample-medium.onnx"
    voice.write_bytes(b"voice")
    config = Path(str(voice) + ".json")
    config.write_text("{}", encoding="utf-8")
    partial = piper / "de_DE-incomplete-medium"
    partial.mkdir()
    (partial / "de_DE-incomplete-medium.onnx").write_bytes(b"incomplete")

    monkeypatch.setattr(inventory, "find_whisper_binary", lambda _: "/bin/whisper-cli")
    monkeypatch.setattr(inventory, "existing_tool", lambda name, runtime: "/bin/ffmpeg")
    monkeypatch.setattr(inventory, "find_system_tool", lambda name: None)
    state = inventory.local_models({
        "whisper_model_path": str(foreign),
        "tts_model_path": str(voice),
        "tts_engine": "piper",
    }, root, available_whisper)

    assert {item["name"] for item in state["whisper"]["models"]} == {"small", "custom"}
    assert next(item for item in state["whisper"]["models"] if item["name"] == "custom")["active"]
    assert state["whisper"]["binary_available"]
    assert state["whisper"]["ffmpeg_available"]
    assert len(state["tts"]["piper_voices"]) == 1
    assert state["tts"]["piper_voices"][0]["path"] == str(voice)
    assert state["tts"]["piper_voices"][0]["paired_config"]
    assert state["tts"]["piper_voices"][0]["verified_playback"] is False
    assert "incomplete" not in str(state["tts"]["piper_voices"])


def test_absent_piper_config_and_binary_flags_remain_unavailable(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    models = root / "models"
    models.mkdir(parents=True)
    voice = models / "test.onnx"
    voice.write_bytes(b"onnx")
    monkeypatch.setattr(inventory, "find_whisper_binary", lambda _: None)
    monkeypatch.setattr(inventory, "existing_tool", lambda name, runtime: None)
    monkeypatch.setattr(inventory, "find_system_tool", lambda name: None)
    state = inventory.local_models({
        "whisper_model_path": str(models / "ggml-small.bin"),
        "tts_model_path": str(voice),
    }, root, models / "ggml-small.bin")
    assert state["whisper"]["models"] == []
    assert state["whisper"]["binary_available"] is False
    assert state["whisper"]["ffmpeg_available"] is False
    assert state["tts"]["piper_voices"] == []
    assert state["tts"]["say_supported"] is False


def test_inventory_is_read_only_and_does_not_scan_outside_project_paths(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    root.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    (other / "ggml-hidden.bin").write_bytes(b"secret")
    monkeypatch.setattr(inventory, "find_whisper_binary", lambda _: None)
    monkeypatch.setattr(inventory, "existing_tool", lambda name, runtime: None)
    state = inventory.local_models({}, root, root / "models" / "ggml-small.bin")
    assert state["whisper"]["models"] == []
    assert state["tts"]["piper_voices"] == []
    assert list(root.iterdir()) == []
