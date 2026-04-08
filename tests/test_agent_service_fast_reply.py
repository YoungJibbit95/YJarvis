from jarvis_agent.agent_service import _quick_local_reply


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
