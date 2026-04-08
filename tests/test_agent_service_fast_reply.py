from jarvis_agent.agent_service import (
    _quick_clarification_reply,
    _quick_local_reply,
    _quick_system_status_reply,
    _quick_utility_reply,
)


def test_quick_reply_for_thanks():
    response = _quick_local_reply("danke dir jarvis")
    assert response is not None
    assert "Sir" in response


def test_quick_reply_for_greeting():
    response = _quick_local_reply("hallo jarvis")
    assert response is not None
    assert "helfen" in response.lower()


def test_quick_reply_ignores_tool_request():
    response = _quick_local_reply("mach eine erinnerung fuer morgen")
    assert response is None


def test_quick_reply_for_capabilities_help():
    response = _quick_local_reply("was kannst du alles?")
    assert response is not None
    assert "Erinnerungen" in response


def test_quick_system_status_reply():
    response = _quick_system_status_reply(
        "welches modell und whisper nutzt du?",
        {
            "model_name": "qwen2.5:3b-instruct",
            "whisper_model_path": "/tmp/ggml-small.bin",
            "tts_engine": "piper",
            "tts_voice": "de_DE-thorsten_emotional-medium",
        },
    )
    assert response is not None
    assert "qwen2.5:3b-instruct" in response
    assert "ggml-small.bin" in response


def test_quick_utility_reply_for_time():
    response = _quick_utility_reply("Jarvis, wie viel Uhr ist es?")
    assert response is not None
    assert "Uhr" in response


def test_quick_clarification_reply_for_vague_reminder():
    response = _quick_clarification_reply("mach mir eine erinnerung")
    assert response is not None
    assert "Erinnerung" in response or "Reminder" in response
