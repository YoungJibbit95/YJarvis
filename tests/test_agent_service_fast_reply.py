from jarvis_agent.conversation_helpers import (
    is_learn_list_request,
    parse_learn_definition_request,
    parse_unlearn_request,
    quick_clarification_reply,
    quick_local_reply,
    quick_system_status_reply,
    quick_utility_reply,
)


def test_quick_reply_for_thanks():
    response = quick_local_reply("danke dir jarvis")
    assert response is not None
    assert "Sir" in response


def test_quick_reply_for_greeting():
    response = quick_local_reply("hallo jarvis")
    assert response is not None
    assert "helfen" in response.lower()


def test_quick_reply_ignores_tool_request():
    response = quick_local_reply("mach eine erinnerung fuer morgen")
    assert response is None


def test_quick_reply_for_capabilities_help():
    response = quick_local_reply("was kannst du alles?")
    assert response is not None
    assert "Erinnerungen" in response
    assert "/learn" in response


def test_quick_system_status_reply():
    response = quick_system_status_reply(
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
    response = quick_utility_reply("Jarvis, wie viel Uhr ist es?")
    assert response is not None
    assert "Uhr" in response


def test_quick_clarification_reply_for_vague_reminder():
    response = quick_clarification_reply("mach mir eine erinnerung")
    assert response is not None
    assert "Erinnerung" in response or "Reminder" in response


def test_parse_learn_definition_slash_format():
    parsed = parse_learn_definition_request('/learn "abendroutine" => oeffne raycast')

    assert parsed is not None
    trigger, action = parsed
    assert trigger == "abendroutine"
    assert action == "oeffne raycast"


def test_parse_learn_definition_natural_language():
    parsed = parse_learn_definition_request(
        'Jarvis, lerne wenn ich "focus mode" sage dann oeffne Notizen'
    )

    assert parsed is not None
    trigger, action = parsed
    assert trigger == "focus mode"
    assert action.lower() == "oeffne notizen"


def test_parse_unlearn_request():
    trigger = parse_unlearn_request('/unlearn "abendroutine"')
    assert trigger == "abendroutine"


def test_is_learn_list_request():
    assert is_learn_list_request("zeige gelernte befehle")
