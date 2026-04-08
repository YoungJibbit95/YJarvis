from __future__ import annotations

import json
import os
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
    return candidate[start : end + 1]


async def stream_chat(
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
) -> AsyncGenerator[str, None]:
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature},
    }
    if DEFAULT_OLLAMA_KEEP_ALIVE:
        payload["keep_alive"] = DEFAULT_OLLAMA_KEEP_ALIVE

    timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=30.0)

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

                    message = chunk.get("message", {})
                    content = message.get("content")
                    if content:
                        yield str(content)

                    if chunk.get("done"):
                        break
    except LlmError:
        raise
    except httpx.HTTPError as error:
        raise LlmError(_friendly_ollama_error(base_url, error)) from error


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


async def plan_tool_call(
    *,
    base_url: str,
    model: str,
    user_message: str,
    tool_specs: list[dict[str, Any]],
) -> dict[str, Any] | None:
    planner_prompt = (
        "Du bist ein Tool Planner. Entscheide, ob ein Tool-Aufruf noetig ist. "
        "Antworte NUR als JSON-Objekt mit Schema: "
        "{\"should_call_tool\":bool,\"tool_name\":string,\"tool_input\":object,\"reason\":string}. "
        "Wenn kein Tool noetig ist, should_call_tool=false und leere Felder setzen."
    )

    planner_messages = [
        {
            "role": "system",
            "content": planner_prompt
            + " Verfuegbare Tools: "
            + json.dumps(tool_specs, ensure_ascii=False),
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]

    raw = await complete_chat(
        base_url=base_url,
        model=model,
        messages=planner_messages,
        temperature=0.0,
        timeout_seconds=25.0,
    )

    blob = _extract_json_blob(raw)
    if not blob:
        return None

    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError:
        return None

    if not parsed.get("should_call_tool"):
        return None

    tool_name = parsed.get("tool_name")
    tool_input = parsed.get("tool_input")

    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return None

    return {
        "tool_name": tool_name,
        "tool_input": tool_input,
        "reason": str(parsed.get("reason", "")),
    }
