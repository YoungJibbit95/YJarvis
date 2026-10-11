"""Exercise the actual Ollama completion parser and approval fallback together."""
import asyncio
import json

import httpx
import pytest

from jarvis_agent import llm
from jarvis_agent.orchestration import legacy_responses
from test_turn_lifecycle import request_approval, rig


def mock_transport(monkeypatch, data, status=200):
    requests, options = [], []
    real_client = httpx.AsyncClient

    def reply(request):
        requests.append(request)
        if isinstance(data, Exception):
            raise data
        return httpx.Response(status, json=data, headers={"location": "https://external.example"})

    def client(**kwargs):
        options.append(kwargs)
        return real_client(**kwargs, transport=httpx.MockTransport(reply))

    monkeypatch.setattr(llm.httpx, "AsyncClient", client)
    return requests, options


def packet(content="Safari ist geöffnet.", **message):
    return {"done": True, "done_reason": "stop", "message": {
        "role": "assistant", "content": content, **message,
    }}


@pytest.mark.parametrize("data", [
    packet(tool_calls=[{"function": {"name": "messages_send", "arguments": {"text": "fake"}}}]),
    packet(tool_calls="malformed"), packet(function_call={"name": "open_url"}),
    packet(content={"text": "not a string"}), packet(content=None), packet(content=""),
    packet(role="tool"), {**packet(), "done": False}, {**packet(), "done_reason": "length"},
    {"done": True, "message": []}, [], None,
    httpx.ConnectError("fixture offline"), httpx.ReadTimeout("fixture read timeout"),
])
def test_invalid_completion_envelope_falls_back_after_one_real_request(rig, monkeypatch, data):
    rig.service = rig.enable("JARVIS_TOOL_SUMMARY_VIA_LLM")
    requests, options = mock_transport(monkeypatch, data)
    monkeypatch.setattr(legacy_responses, "complete_chat", llm.complete_chat)

    async def scenario():
        approval_id = await request_approval(rig)
        await rig.service.handle_approval_decision(approval_id, "approve")
        assert len(requests) == 1
        assert options[0]["trust_env"] is False
        assert options[0]["follow_redirects"] is False
        rig.tools.execute.assert_awaited_once()
        rig.db.add_tool_run.assert_awaited_once()
        assert rig.db.add_tool_run.call_args.kwargs["success"] is True
        assert [e["content"] for e in rig.events if e["event"] == "message"] == [
            "Tool `open_app` ausgefuehrt. Ergebnis: Erledigt"
        ]
        assert rig.events[-1]["state"] == "done"

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [301, 302, 307, 308, 400, 500])
def test_redirect_or_http_failure_never_forwards_evidence_or_retries(monkeypatch, status):
    requests, _ = mock_transport(monkeypatch, packet(), status)
    with pytest.raises(llm.LlmError):
        asyncio.run(llm.complete_chat(
            base_url="http://127.0.0.1:11434", model="fixture", messages=[], text_only=True,
        ))
    assert len(requests) == 1
    assert requests[0].url.host == "127.0.0.1"


def test_text_only_completion_has_one_request_keep_alive_and_no_tool_descriptions(monkeypatch):
    requests, options = mock_transport(monkeypatch, packet())
    result = asyncio.run(llm.complete_chat(
        base_url="http://127.0.0.1:11434", model="fixture", messages=[],
        temperature=0.1, timeout_seconds=8, text_only=True,
    ))
    assert result == "Safari ist geöffnet."
    assert len(requests) == 1
    payload = json.loads(requests[0].content)
    assert payload["stream"] is False
    assert "tools" not in payload
    assert payload["options"] == {"temperature": 0.1, "num_predict": 256}
    if llm.DEFAULT_OLLAMA_KEEP_ALIVE:
        assert payload["keep_alive"] == llm.DEFAULT_OLLAMA_KEEP_ALIVE
    assert options[0]["timeout"].read == 8


def test_other_completion_callers_retain_original_contract(monkeypatch):
    requests, options = mock_transport(monkeypatch, {"message": {"content": '{"decision":"conversation"}'}})
    assert asyncio.run(llm.complete_chat(
        base_url="http://fixture", model="fixture", messages=[],
    )) == '{"decision":"conversation"}'
    assert "trust_env" not in options[0]
    assert "num_predict" not in json.loads(requests[0].content)["options"]
