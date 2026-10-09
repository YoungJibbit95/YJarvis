"""Existing prompt, streaming and event output, extracted without new protocols."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any

from ..conversation_helpers import normalize_honorifics, tool_performance_score
from ..db import Database
from ..events import EventBus
from ..llm import LlmError, ModelToolCall, complete_chat, stream_chat
from ..memory import load_context_snippets, maybe_compact_session
from ..profile import build_persona_system_prompt
from ..runtime_facts import ReadOnlyToolkit, required_live_fact_tool


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LegacyResponses:
    def __init__(
        self,
        db: Database,
        event_bus: EventBus,
        *,
        history_limit: int,
        memory_limit: int,
        enable_llm_tool_summary: bool,
        token_flush_interval_seconds: float,
        token_flush_min_chars: int,
        read_only_toolkit: ReadOnlyToolkit | None = None,
    ) -> None:
        self.db = db
        self.event_bus = event_bus
        self.history_limit = history_limit
        self.memory_limit = memory_limit
        self.enable_llm_tool_summary = enable_llm_tool_summary
        self.token_flush_interval_seconds = token_flush_interval_seconds
        self.token_flush_min_chars = token_flush_min_chars
        self.read_only_toolkit = read_only_toolkit or ReadOnlyToolkit()

    async def emit_state(
        self,
        *,
        session_id: str,
        run_id: str,
        state: str,
        detail: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "event": "run_state",
            "run_id": run_id,
            "state": state,
            "detail": detail,
            "timestamp": utc_now_iso(),
        }
        if data is not None:
            payload["data"] = data
        await self.event_bus.publish(session_id, payload)

    async def emit_token(self, session_id: str, run_id: str, token: str) -> None:
        await self.event_bus.publish(
            session_id,
            {
                "event": "token",
                "run_id": run_id,
                "token": token,
                "timestamp": utc_now_iso(),
            },
        )

    async def emit_message(self, session_id: str, run_id: str, content: str) -> None:
        await self.event_bus.publish(
            session_id,
            {
                "event": "message",
                "run_id": run_id,
                "role": "assistant",
                "content": content,
                "timestamp": utc_now_iso(),
            },
        )

    async def _build_prompt_messages(
        self,
        session_id: str,
        user_message: str,
        profile: dict[str, Any],
    ) -> list[dict[str, str]]:
        # Read-only, independently connected SQLite queries may overlap. Keep
        # the same limits/content and avoid an extra LLM request.
        history, memories, learned_tool_stats = await asyncio.gather(
            self.db.list_recent_messages(session_id, limit=self.history_limit),
            load_context_snippets(
                self.db, user_message, limit=self.memory_limit, session_id=session_id
            ),
            self.db.get_tool_learning_stats(),
        )

        system_parts = [
            build_persona_system_prompt(profile),
"Fuer aktuelle Systemzeit, Datum oder Systemfaehigkeiten fordere verifizierte Fakten ueber die angebotenen read-only Toolkit-Tools an. Erfinde solche Werte nicht.",
            "Normale Gespraeche beantwortest du selbst. Kein Python-Template beantwortet sie. Aus der Existenz eines Tools folgt keine Ausfuehrungsfreigabe.",
            "Wenn ein anderes OS-Tool noetig ist, nutze die bestehende Freigaberoute statt Halluzination.",
            "Antworte standardmaessig kurz und direkt (maximal 4 Saetze), ausser der Nutzer fordert Details.",
            "Wenn Fakten unsicher sind, benenne Unsicherheit klar. Erfinde keine Quellen, Namen oder Ereignisse.",
            "Nutze fuer kurze Anschlussfragen wie Warum, Erklaer es einfacher oder Mach es kuerzer die letzten Nachrichten dieser Session.",
            "Beziehe dich nur auf erkennbar passende Aussagen; falls mehrere Bezuege moeglich sind, frage einmal kurz nach.",
            "Ein Bezug auf vorige Nachrichten allein autorisiert keine Computeraktion und umgeht keine Freigabe.",
            "Wenn die Anfrage mehrdeutig ist, stelle genau eine kurze Rueckfrage statt Annahmen zu treffen.",
        ]

        if memories:
            system_parts.append("Kontext-Erinnerungen:")
            for memory in memories:
                system_parts.append(f"- {memory}")

        if learned_tool_stats:
            ranked_stats = sorted(
                learned_tool_stats,
                key=tool_performance_score,
                reverse=True,
            )
            system_parts.append(
                "Lernsignale aus lokalen Ausfuehrungen (bevorzuge robuste und schnelle Wege):"
            )
            for row in ranked_stats[:5]:
                success_count = int(row.get("success_count", 0))
                failure_count = int(row.get("failure_count", 0))
                total = max(1, success_count + failure_count)
                success_rate = int(round((success_count / total) * 100))
                latency = int(round(float(row.get("average_latency_ms", 0.0) or 0.0)))
                system_parts.append(
                    f"- {row.get('tool_name', '-')}: {success_rate}% Erfolg, {latency} ms Durchschnitt"
                )

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": "\n".join(system_parts),
            }
        ]

        for row in history:
            role = str(row.get("role", ""))
            content = str(row.get("content", ""))
            if role not in {"user", "assistant"} or not content:
                continue
            messages.append({"role": role, "content": content})

        return messages

    async def compose_tool_response(
        self,
        *,
        settings: dict[str, Any],
        profile: dict[str, Any],
        tool_name: str,
        tool_input: dict[str, Any],
        tool_output: str,
    ) -> str:
        base_url = str(settings.get("ollama_base_url", "http://127.0.0.1:11434"))
        model = str(settings.get("model_name", "qwen2.5:3b-instruct"))

        prompt_messages = [
            {
                "role": "system",
                "content": (
                    build_persona_system_prompt(profile)
                    + "\nFormuliere eine kurze deutsche Rueckmeldung zur Tool-Ausfuehrung."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Tool: {tool_name}\n"
                    f"Input: {tool_input}\n"
                    f"Output: {tool_output}\n"
                    "Antworte in 1-3 Saetzen."
                ),
            },
        ]

        if not self.enable_llm_tool_summary:
            return normalize_honorifics(f"Aktion abgeschlossen ({tool_name}). Ergebnis: {tool_output}")

        try:
            response = await complete_chat(
                base_url=base_url,
                model=model,
                messages=prompt_messages,
                temperature=0.1,
                timeout_seconds=20.0,
            )
            if response.strip():
                return normalize_honorifics(response)
        except Exception:
            pass

        return normalize_honorifics(f"Tool `{tool_name}` ausgefuehrt. Ergebnis: {tool_output}")

    async def stream_response(
        self,
        session_id: str,
        run_id: str,
        user_message: str,
        profile: dict[str, Any],
        settings: dict[str, Any],
    ) -> None:
        base_url = str(settings.get("ollama_base_url", "http://127.0.0.1:11434"))
        model = str(settings.get("model_name", "qwen2.5:3b-instruct"))
        required_tool = required_live_fact_tool(user_message)

        try:
            messages = await self._build_prompt_messages(session_id, user_message, profile)
            assistant_text = ""
            pending_token_buffer = ""
            last_token_flush = time.perf_counter()
            first_visible_token_sent = False

            async def flush_token_buffer(force: bool = False) -> None:
                nonlocal pending_token_buffer, last_token_flush
                if not pending_token_buffer:
                    return
                if not force:
                    now = time.perf_counter()
                    if (
                        len(pending_token_buffer) < self.token_flush_min_chars
                        and (now - last_token_flush) < self.token_flush_interval_seconds
                    ):
                        return
                await self.emit_token(session_id, run_id, pending_token_buffer)
                pending_token_buffer = ""
                last_token_flush = time.perf_counter()

            async def add_token(token: str) -> None:
                nonlocal assistant_text, pending_token_buffer, first_visible_token_sent
                if not token:
                    return
                assistant_text += token
                pending_token_buffer += token
                await flush_token_buffer(force=not first_visible_token_sent)
                first_visible_token_sent = True

            # Fact-sensitive turns are a distinct, fully withheld decision
            # pass: NO WebSocket/TTS tokens before validating a real Toolkit
            # result. Ordinary chat has NO native tools on offer, so it can
            # still stream the first token immediately in one model call.
            # This is an integrity gate, never a Python-written answer.
            first_call: dict[str, Any] = {
                "base_url": base_url, "model": model, "messages": messages,
            }
            if required_tool is not None:
                first_call["tools"] = self.read_only_toolkit.descriptions()

            requested_tool: ModelToolCall | None = None
            unverified_text = ""
            async for part in stream_chat(**first_call):
                if isinstance(part, ModelToolCall):
                    if required_tool is None:
                        raise LlmError("Unangeforderter Modell-Tool-Aufruf im Gespraech")
                    if requested_tool is not None or assistant_text or unverified_text:
                        raise LlmError("Vermischte oder mehrfache Modell-Tool-Ausgabe")
                    requested_tool = part
                elif isinstance(part, str):
                    if requested_tool is not None:
                        raise LlmError("Modell antwortete nach Tool-Aufruf ohne Pruefung")
                    if required_tool:
                        # Never expose a guessed current time/capability claim.
                        unverified_text += part
                        if len(unverified_text) > 4096:
                            raise LlmError("Unverifizierte Modellantwort zu lang")
                    else:
                        await add_token(part)
                else:
                    raise LlmError("Unerwartetes Modell-Streaming-Format")

            if requested_tool is not None:
                if required_tool and requested_tool.name != required_tool:
                    raise LlmError("Falsche Faktenquelle fuer die Anfrage")
                if assistant_text or unverified_text:
                    raise LlmError("Modell mischte Text mit einem Tool-Aufruf")
                try:
                    facts = self.read_only_toolkit.execute(
                        requested_tool.name, requested_tool.arguments, settings=settings,
                    )
                except (TypeError, ValueError) as error:
                    raise LlmError("Tool-Aufruf abgelehnt: ungepruefte Funktion oder Argumente") from error

                # A single, non-recursive read-only call. Legacy OS actions are
                # intentionally absent from this dispatcher and still need
                # the existing separate human Approval.
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "type": "function",
                        "function": {
                            "name": requested_tool.name,
                            "arguments": requested_tool.arguments,
                        },
                    }],
                })
                messages.append({
                    "role": "tool",
                    "tool_name": requested_tool.name,
                    "content": json.dumps(facts, ensure_ascii=False),
                })
                async for part in stream_chat(
                    base_url=base_url, model=model, messages=messages,
                ):
                    if not isinstance(part, str):
                        raise LlmError("Mehrfache Tool-Aktionen sind nicht erlaubt")
                    await add_token(part)
            elif required_tool:
                # A local model without reliable tool calling does not get to
                # invent a current clock value or claim OS capabilities.
                raise LlmError("Aktuelle Fakten nicht verifiziert: kein Toolkit-Aufruf vom Modell")

            await flush_token_buffer(force=True)

            assistant_text = normalize_honorifics(assistant_text)
            if not assistant_text:
                raise LlmError("Ollama hat keine verwertbare Modellantwort geliefert")

            await self.finish(
                session_id, run_id, assistant_text,
                detail="Antwort abgeschlossen",
            )
            await maybe_compact_session(self.db, session_id)
        except LlmError as error:
            fallback = normalize_honorifics(f"LLM Fehler: {error}")
            await self.finish(
                session_id, run_id, fallback,
                state="error",
                detail="LLM Anfrage fehlgeschlagen",
            )
        except Exception as error:
            fallback = normalize_honorifics(f"Unerwarteter Fehler: {error}")
            await self.finish(
                session_id, run_id, fallback,
                state="error",
                detail="Unbekannter Verarbeitungsfehler",
            )

    async def finish(
        self,
        session_id: str,
        run_id: str,
        content: str,
        *,
        detail: str,
        state: str = "done",
    ) -> None:
        # Persistence must precede message publication and the terminal state.
        await self.db.add_message(session_id=session_id, role="assistant", content=content)
        await self.emit_message(session_id, run_id, content)
        await self.emit_state(session_id=session_id, run_id=run_id, state=state, detail=detail)
