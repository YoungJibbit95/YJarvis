from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, AsyncGenerator

import httpx


class LlmError(RuntimeError):
    pass


DEFAULT_OLLAMA_KEEP_ALIVE = os.environ.get("JARVIS_OLLAMA_KEEP_ALIVE", "30m").strip()


def _friendly_ollama_error(base_url: str, error: Exception) -> str:
    normalized_base_url = base_url.rstrip("/")

    if isinstance(error, httpx.ConnectError):
        return (
            f"Ollama ist unter {normalized_base_url} nicht erreichbar. "
            "Bitte `ollama serve` starten und Modell-Verfuegbarkeit pruefen."
        )

    if isinstance(error, httpx.TimeoutException):
        return f"Ollama Timeout unter {normalized_base_url}. Bitte Anfrage/Modellgroesse pruefen."

    return f"Ollama Anfrage fehlgeschlagen: {error}"


def _extract_json_blob(text: str) -> str | None:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    re@dataclass(frozen=True)
class ModelToolCall:
    """Only a proposal; the exact read-only dispatcher must validate it."""

    name: str
    arguments: Any


def _single_model_tool_call(chunks: list[Any]) -> ModelToolCall:
    # Streaming Ollama may send the function in one chunk or in fragments.
    # Never accept multiple tool calls or silently execute any partial output.
    if not 1 <= len(chunks) <= 16:
        raise LlmError("Read-only tool request must be exactly one call")

    names: list[str] = []
    arguments: list[Any] = []
    indices: set[int] = set()
    for item in chunks:
        if not isinstance(item, dict):
            raise LlmError("Invalid tool call")
        function = item.get("function")
        if not isinstance(function, dict):
            raise LlmError("Invalid function call")
        index = function.get("index", item.get("index", 0))
        if type(index) is not int or index != 0:
            raise LlmError("Multiple tool calls are not permitted")
        indices.add(index)
        name = function.get("name", "")
        if not isinstance(name, str):
            raise LlmError("Invalid function name")
        if name:
            names.append(name)
        if "arguments" in function:
            arguments.append(function["arguments"])
    if not names or len(set(names)) != 1 or indices != {0}:
        raise LlmError("Invalid or multiple tool names")
    if not arguments:
        raise LlmError("Missing tool arguments")
    if len(arguments) == 1:
        arg = arguments[0]
    elif all(isinstance(part, str) for part in arguments):
        arg = "".join(arguments)
    elif all(part == arguments[0] for part in arguments):
        arg = arguments[0]
    else:
        raise LlmError("Inconsistent tool arguments")

    if isinstance(arg, str):
        if len(arg) > 1024:
            raise LlmError("Tool argument limit exceeded")
        try:
            arg = json.loads(arg, object_pairs_hook=_unique_json_fields)
        except (ValueError, TypeError) as error:
            raise LlmError("Invalid tool argument JSON") from error
    if type(arg) is not dict:
        raise LlmError("Tool arguments must be an object")
    return ModelToolCall(names[0], arg)


async def stream_chat(
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.2,
    tools: list[dict[str, Any]] | None = None,
) -> AsyncGenerator[str | ModelToolCall, None]:
    url = f"{base_url.rstrip('/')}/api/chat"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature},
    }
    if tools is not None:
        payload["tools"] = tools
    if DEFAULT_OLLAMA_KEEP_ALIVE:
        payload["keep_alive"] = DEFAULT_OLLAMA_KEEP_ALIVE

    timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=30.0)
    tool_chunks: list[Any] = []

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code >= 400:
                    details = await response.aread()
                    raise LlmError(
                        f"Ollama stream error {response.status_code}: {details.decode('utf-8', errors='ignore')}"
                    )

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(chunk, dict):
                        continue
                    message = chunk.get("message", {})
                    if not isinstance(message, dict):
                        continue

                    calls = message.get("tool_calls")
                    if calls is not None:
                        if not isinstance(calls, list):
                            raise LlmError("Invalid model tool calls")
                        tool_chunks.extend(calls)
                        if len(tool_chunks) > 16:
                            raise LlmError("Excessive model tool calls")
                    content = message.get("content")
                    if content:
                        yield str(content)

                    if chunk.get("done"):
                        break
    except LlmError:
        raise
    except httpx.HTTPError as error:
        raise LlmError(_friendly_ollama_error(base_url, error)) from error

    if tool_chunks:
        yield _single_model_tool_call(tool_chunks)


or(base_url, error)) from error


async def complete_chat(
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    timeout_seconds: float = 180.0,
) -> str:
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if DEFAULT_OLLAMA_KEEP_ALIVE:
        payload["keep_alive"] = DEFAULT_OLLAMA_KEEP_ALIVE

    timeout = httpx.Timeout(connect=10.0, read=timeout_seconds, write=30.0, pool=30.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
    except httpx.HTTPError as error:
        raise LlmError(_friendly_ollama_error(base_url, error)) from error

    if response.status_code >= 400:
        raise LlmError(
            f"Ollama completion error {response.status_code}: {response.text}"
        )

    data = response.json()
    return str(data.get("message", {}).get("content", "")).strip()


def _unique_json_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


async def plan_tool_call(
    *,
    base_url: str,
    model: str,
    user_message: str,
    tool_specs: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """One bounded, non-streaming interpretation; no executable free text."""
    if not tool_specs or len(user_message) > 350:
        return None

    planner_prompt = (
        "Du klassifizierst NUR einen ausdruecklichen, unklaren Computerauftrag. "
        "Antworte ausschliesslich mit EINEM JSON-Objekt, ohne Markdown, Erklaerung "
        "oder Gedankengang. Genau eine Form: "
        '{"decision":"conversation"} ODER '
        '{"decision":"clarify","question":"Eine kurze Frage?"} ODER '
        '{"decision":"tool","tool_name":"aus_allowlist","tool_input":{}}. '
        "Die Tool-Argumente muessen im Benutzertext ausdruecklich stehen; "
        "keine App, URL, Person, Menge oder Datei erfinden. "
        "Falls unklar, nur eine Rueckfrage oder conversation. "
        "Nie mehrere Tools, Shell, Code oder Aktionsfreigaben erzeugen. "
        "Erlaubte Tools mit rein informellen Feldtypen: "
        + json.dumps(tool_specs, ensure_ascii=False, separators=(",", ":"))
    )
    raw = await complete_chat(
        base_url=base_url,
        model=model,
        messages=[
            {"role": "system", "content": planner_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.0,
        timeout_seconds=8.0,
    )
    if not isinstance(raw, str) or not 2 <= len(raw) <= 4096:
        return None
    try:
        data = json.loads(
            raw.strip(),
            object_pairs_hook=_unique_json_fields,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")),
        )
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None
