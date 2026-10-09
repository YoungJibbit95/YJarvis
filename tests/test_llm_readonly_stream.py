"""Ollama streaming: content remains streamed; native model tools are proposals only."""
import asyncio
import json
from contextlib import asynccontextmanager

import pytest

from jarvis_agent import llm
from jarvis_agent.llm import LlmError, ModelToolCall


class FakeStreamResponse:
    status_code = 200

    def __init__(self, chunks):
        self.chunks = chunks

    async def aiter_lines(self):
        for chunk in self.chunks:
            yield json.dumps(chunk, ensure_ascii=False)


class FakeClient:
    def __init__(self, chunks, sent):
        self.chunks = chunks
        self.sent = sent

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    @asynccontextmanager
    async def stream(self, method, url, *, json):
        self.sent.append((method, url, json))
        yield FakeStreamResponse(self.chunks)


def make_client(monkeypatch, chunks):
    sent = []
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kwargs: FakeClient(chunks, sent))
    return sent


def packet(*, content=None, tool_calls=None, done=False):
    message = {"role": "assistant"}
    if content is not None:
        message["content"] = content
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {"message": message, "done": done}


def tool_call(name, args, index=0):
    return {"type": "function", "function": {"index": index, "name": name, "arguments": args}}


def test_one_model_request_streams_regular_conversation_directly(monkeypatch):
    sent = make_client(monkeypatch, [
        packet(content="Hallo ", done=False),
        packet(content="zurück!", done=False),
        packet(done=True),
    ])
    tools = [{"type": "function", "function": {"name": "system.local_datetime"}}]

    async def scenario():
        return [part async for part in llm.stream_chat(
            base_url="http://localhost:11434", model="test",
            messages=[{"role": "user", "content": "Hallo"}], tools=tools,
        )]

    assert asyncio.run(scenario()) == ["Hallo ", "zurück!"]
    assert len(sent) == 1
    assert sent[0][0] == "POST"
    assert sent[0][2]["stream"] is True
    assert sent[0][2]["tools"] == tools
    assert sent[0][2]["messages"][-1]["content"] == "Hallo"
    assert sent[0][2]["keep_alive"] == llm.DEFAULT_OLLAMA_KEEP_ALIVE or not llm.DEFAULT_OLLAMA_KEEP_ALIVE


def test_streaming_native_tool_call_produces_validated_event_not_text(monkeypatch):
    sent = make_client(monkeypatch, [
        packet(tool_calls=[tool_call("system.local_datetime", {})]),
        packet(done=True),
    ])

    async def scenario():
        return [part async for part in llm.stream_chat(
            base_url="http://localhost:11434", model="test",
            messages=[{"role": "user", "content": "Wie spät ist es?"}], tools=[],
        )]

    assert asyncio.run(scenario()) == [ModelToolCall("system.local_datetime", {})]
    assert len(sent) == 1


@pytest.mark.parametrize("calls", [
    [tool_call("system.local_datetime", {}), tool_call("system.local_datetime", {})],
    [tool_call("open_app", {"app_name": "Safari"}), tool_call("system.local_datetime", {}, 1)],
    [tool_call("system.local_datetime", {"execute": True}, 2)],
    [{"type": "function", "function": {"arguments": {}}}],
    [tool_call("system.local_datetime", "not json")],
    [tool_call("system.local_datetime", [])],
])
def test_ill_formed_or_multiple_tool_calls_fail_closed(monkeypatch, calls):
    make_client(monkeypatch, [packet(tool_calls=calls), packet(done=True)])

    async def scenario():
        return [part async for part in llm.stream_chat(
            base_url="http://localhost:11434", model="test", messages=[], tools=[],
        )]

    with pytest.raises(LlmError):
        asyncio.run(scenario())


def test_streaming_fragmented_single_tool_arguments_preserves_exact_identity(monkeypatch):
    make_client(monkeypatch, [
        packet(tool_calls=[tool_call("system.local_datetime", "{")]),
        packet(tool_calls=[tool_call("system.local_datetime", "}")]),
        packet(done=True),
    ])

    async def scenario():
        return [part async for part in llm.stream_chat(
            base_url="http://localhost:11434", model="test", messages=[], tools=[],
        )]

    assert asyncio.run(scenario()) == [ModelToolCall("system.local_datetime", {})]


def test_duplicate_full_tool_calls_in_separate_stream_chunks_are_rejected(monkeypatch):
    make_client(monkeypatch, [
        packet(tool_calls=[tool_call("system.local_datetime", {})]),
        packet(tool_calls=[tool_call("system.local_datetime", {})]),
        packet(done=True),
    ])

    async def scenario():
        return [part async for part in llm.stream_chat(
            base_url="http://localhost:11434", model="test", messages=[], tools=[],
        )]

    with pytest.raises(LlmError, match="Multiple complete tool calls"):
        asyncio.run(scenario())


def test_full_tool_call_followed_by_second_distinct_call_is_rejected(monkeypatch):
    make_client(monkeypatch, [
        packet(tool_calls=[tool_call("system.local_datetime", {})]),
        packet(tool_calls=[tool_call("toolkit.capability_snapshot", {})]),
        packet(done=True),
    ])

    async def scenario():
        return [part async for part in llm.stream_chat(
            base_url="http://localhost:11434", model="test", messages=[], tools=[],
        )]

    with pytest.raises(LlmError):
        asyncio.run(scenario())
