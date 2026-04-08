from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .conversation_helpers import (
    looks_like_tool_request,
    normalize_honorifics,
    quick_clarification_reply,
    quick_local_reply,
    quick_system_status_reply,
    quick_utility_reply,
    tool_performance_score,
)
from .db import Database
from .events import EventBus
from .learning_engine import LearningEngine
from .llm import LlmError, complete_chat, plan_tool_call, stream_chat
from .memory import load_context_snippets, maybe_compact_session
from .profile import build_persona_system_prompt, load_profile
from .safety import (
    confirmation_message,
    detect_blocked_user_request,
    detect_confirmation_required_request,
    is_confirmation_message,
    refusal_message,
)
from .tool_intent import ToolCallIntent, infer_heuristic_tool_call
from .tools import ToolRegistry


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentService:
    def __init__(
        self,
        db: Database,
        event_bus: EventBus,
        tools: ToolRegistry,
        profile_path: Path,
    ) -> None:
        self.db = db
        self.event_bus = event_bus
        self.tools = tools
        self.profile_path = profile_path
        self.learning = LearningEngine(db, tools)

        self.pending_confirmations: dict[str, dict[str, str]] = {}
        self.history_limit = max(3, int(os.environ.get("JARVIS_HISTORY_LIMIT", "6")))
        self.memory_limit = max(1, int(os.environ.get("JARVIS_MEMORY_LIMIT", "1")))
        self.enable_tool_planner = (
            os.environ.get("JARVIS_ENABLE_TOOL_PLANNER", "0").strip().lower() in {"1", "true", "yes", "on"}
        )
        self.enable_llm_tool_summary = (
            os.environ.get("JARVIS_TOOL_SUMMARY_VIA_LLM", "0").strip().lower() in {"1", "true", "yes", "on"}
        )
        self.token_flush_interval_seconds = max(
            0.01,
            float(os.environ.get("JARVIS_TOKEN_FLUSH_INTERVAL_MS", "20")) / 1000.0,
        )
        self.token_flush_min_chars = max(
            1,
            int(os.environ.get("JARVIS_TOKEN_FLUSH_MIN_CHARS", "8")),
        )

    def _load_profile(self) -> dict[str, Any]:
        return load_profile(self.profile_path)

    async def _emit_state(
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

    async def _emit_token(self, session_id: str, run_id: str, token: str) -> None:
        await self.event_bus.publish(
            session_id,
            {
                "event": "token",
                "run_id": run_id,
                "token": token,
                "timestamp": utc_now_iso(),
            },
        )

    async def _emit_message(self, session_id: str, run_id: str, content: str) -> None:
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
        history = await self.db.list_recent_messages(session_id, limit=self.history_limit)
        memories = await load_context_snippets(self.db, user_message, limit=self.memory_limit)
        learned_tool_stats = await self.db.get_tool_learning_stats()

        system_parts = [
            build_persona_system_prompt(profile),
            "Wenn ein Tool noetig ist, nutze die Tool-Route statt Halluzination.",
            "Antworte standardmaessig kurz und direkt (maximal 4 Saetze), ausser der Nutzer fordert Details.",
            "Wenn Fakten unsicher sind, benenne Unsicherheit klar. Erfinde keine Quellen, Namen oder Ereignisse.",
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

    async def _decide_tool_intent(
        self,
        user_message: str,
        settings: dict[str, Any],
        allow_learned_commands: bool = True,
    ) -> ToolCallIntent | None:
        if allow_learned_commands:
            learned_intent = await self.learning.resolve_learned_command_intent(user_message)
            if learned_intent:
                return await self.learning.apply_adaptive_routing(learned_intent)

        heuristic_intent = infer_heuristic_tool_call(user_message)
        if heuristic_intent and self.tools.has_tool(heuristic_intent.tool_name):
            return await self.learning.apply_adaptive_routing(heuristic_intent)
        if heuristic_intent and not self.tools.has_tool(heuristic_intent.tool_name):
            heuristic_intent = None

        if not self.enable_tool_planner:
            return heuristic_intent

        if not looks_like_tool_request(user_message):
            return heuristic_intent

        ranked_tool_specs = await self.learning.rank_tool_specs_for_planner(self.tools.list_specs())
        try:
            planned = await plan_tool_call(
                base_url=str(settings.get("ollama_base_url", "http://127.0.0.1:11434")),
                model=str(settings.get("model_name", "qwen2.5:3b-instruct")),
                user_message=user_message,
                tool_specs=ranked_tool_specs,
            )
        except Exception:
            return heuristic_intent

        if not planned:
            return heuristic_intent

        tool_name = str(planned.get("tool_name", "")).strip()
        tool_input = planned.get("tool_input")
        reason = str(planned.get("reason", "LLM Planner"))

        if not tool_name or not isinstance(tool_input, dict):
            return heuristic_intent

        if not self.tools.has_tool(tool_name):
            return heuristic_intent

        intent = ToolCallIntent(
            tool_name=tool_name,
            tool_input=tool_input,
            reason=reason,
        )
        return await self.learning.apply_adaptive_routing(intent)

    async def start_run(self, session_id: str, run_id: str, user_message: str) -> None:
        await self.db.add_message(session_id=session_id, role="user", content=user_message)
        await self._emit_state(
            session_id=session_id,
            run_id=run_id,
            state="received",
            detail="Nachricht empfangen",
        )

        await self._emit_state(
            session_id=session_id,
            run_id=run_id,
            state="thinking",
            detail="Analysiere Anfrage",
        )

        profile = self._load_profile()
        settings = await self.db.get_settings()
        normalized_user_message = user_message
        was_policy_confirmed = False

        pending_confirmation = self.pending_confirmations.get(session_id)
        if pending_confirmation:
            if is_confirmation_message(user_message, profile):
                normalized_user_message = pending_confirmation.get("original_message", user_message)
                was_policy_confirmed = True
                self.pending_confirmations.pop(session_id, None)
                await self._emit_state(
                    session_id=session_id,
                    run_id=run_id,
                    state="thinking",
                    detail="Sicherheitsbestaetigung akzeptiert",
                )
            else:
                self.pending_confirmations.pop(session_id, None)

        blocked_reason = detect_blocked_user_request(normalized_user_message, profile)
        if blocked_reason:
            blocked_text = normalize_honorifics(refusal_message(profile, reason=blocked_reason))
            await self.db.add_message(session_id=session_id, role="assistant", content=blocked_text)
            await self._emit_message(session_id, run_id, blocked_text)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="done",
                detail="Sicherheitsregel hat Anfrage blockiert",
            )
            return

        if not was_policy_confirmed:
            confirm_reason = detect_confirmation_required_request(normalized_user_message, profile)
            if confirm_reason:
                self.pending_confirmations[session_id] = {
                    "original_message": normalized_user_message,
                    "reason": confirm_reason,
                }
                ask_text = normalize_honorifics(confirmation_message(profile, reason=confirm_reason))
                await self.db.add_message(session_id=session_id, role="assistant", content=ask_text)
                await self._emit_message(session_id, run_id, ask_text)
                await self._emit_state(
                    session_id=session_id,
                    run_id=run_id,
                    state="done",
                    detail="Sicherheitsbestaetigung erforderlich",
                )
                return

        learning_response = await self.learning.handle_learning_instruction(
            user_message=normalized_user_message,
            settings=settings,
            decide_tool_intent=self._decide_tool_intent,
        )
        if learning_response:
            learning_text = normalize_honorifics(learning_response)
            await self.db.add_message(session_id=session_id, role="assistant", content=learning_text)
            await self._emit_message(session_id, run_id, learning_text)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="done",
                detail="Lernmodus aktualisiert",
            )
            return

        quick_reply = quick_local_reply(normalized_user_message)
        if quick_reply:
            quick_text = normalize_honorifics(quick_reply)
            await self.db.add_message(session_id=session_id, role="assistant", content=quick_text)
            await self._emit_message(session_id, run_id, quick_text)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="done",
                detail="Schnellantwort lokal",
            )
            return

        quick_status = quick_system_status_reply(normalized_user_message, settings)
        if quick_status:
            quick_text = normalize_honorifics(quick_status)
            await self.db.add_message(session_id=session_id, role="assistant", content=quick_text)
            await self._emit_message(session_id, run_id, quick_text)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="done",
                detail="Statusantwort lokal",
            )
            return

        quick_utility = quick_utility_reply(normalized_user_message)
        if quick_utility:
            quick_text = normalize_honorifics(quick_utility)
            await self.db.add_message(session_id=session_id, role="assistant", content=quick_text)
            await self._emit_message(session_id, run_id, quick_text)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="done",
                detail="Utility-Antwort lokal",
            )
            return

        clarification = quick_clarification_reply(normalized_user_message)
        if clarification:
            clarification_text = normalize_honorifics(clarification)
            await self.db.add_message(session_id=session_id, role="assistant", content=clarification_text)
            await self._emit_message(session_id, run_id, clarification_text)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="done",
                detail="Rueckfrage fuer praezisen Auftrag",
            )
            return

        intent = await self._decide_tool_intent(normalized_user_message, settings)

        if intent and self.tools.has_tool(intent.tool_name):
            self.learning.mark_pending_trigger(run_id, intent.source_trigger)
            approval_id = str(uuid.uuid4())
            approval = await self.db.create_approval(
                approval_id=approval_id,
                session_id=session_id,
                run_id=run_id,
                tool_name=intent.tool_name,
                tool_input=intent.tool_input,
            )
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="approval_required",
                detail=f"Freigabe erforderlich: {intent.tool_name}",
                data={
                    "approval": approval,
                    "reason": intent.reason,
                },
            )
            return

        if intent is None and looks_like_tool_request(normalized_user_message):
            clarification_text = normalize_honorifics(
                "Ich habe den Tool-Aufruf nicht eindeutig erkannt und fuehre daher nichts blind aus. "
                "Formulieren Sie bitte konkret, z. B. `Oeffne Safari` oder `Oeffne die App Notizen`."
            )
            await self.db.add_message(session_id=session_id, role="assistant", content=clarification_text)
            await self._emit_message(session_id, run_id, clarification_text)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="done",
                detail="Tool-Aufruf unklar, keine Ausfuehrung",
            )
            return

        base_url = str(settings.get("ollama_base_url", "http://127.0.0.1:11434"))
        model = str(settings.get("model_name", "qwen2.5:3b-instruct"))

        try:
            messages = await self._build_prompt_messages(session_id, normalized_user_message, profile)
            assistant_text = ""
            pending_token_buffer = ""
            last_token_flush = time.perf_counter()

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

                await self._emit_token(session_id, run_id, pending_token_buffer)
                pending_token_buffer = ""
                last_token_flush = time.perf_counter()

            async for token in stream_chat(base_url=base_url, model=model, messages=messages):
                assistant_text += token
                pending_token_buffer += token
                await flush_token_buffer(force=False)

            await flush_token_buffer(force=True)

            assistant_text = normalize_honorifics(assistant_text)
            if not assistant_text:
                assistant_text = "Ich konnte lokal keine Antwort erzeugen. Bitte pruefe Ollama und das Modell."

            await self.db.add_message(
                session_id=session_id,
                role="assistant",
                content=assistant_text,
            )
            await self._emit_message(session_id, run_id, assistant_text)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="done",
                detail="Antwort abgeschlossen",
            )
            await maybe_compact_session(self.db, session_id)
        except LlmError as error:
            fallback = normalize_honorifics(f"LLM Fehler: {error}")
            await self.db.add_message(session_id=session_id, role="assistant", content=fallback)
            await self._emit_message(session_id, run_id, fallback)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="error",
                detail="LLM Anfrage fehlgeschlagen",
            )
        except Exception as error:
            fallback = normalize_honorifics(f"Unerwarteter Fehler: {error}")
            await self.db.add_message(session_id=session_id, role="assistant", content=fallback)
            await self._emit_message(session_id, run_id, fallback)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="error",
                detail="Unbekannter Verarbeitungsfehler",
            )

    async def _compose_tool_response(
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

    async def handle_approval_decision(self, approval_id: str, decision: str) -> str:
        approval = await self.db.get_approval(approval_id)
        if approval is None:
            raise ValueError("Approval nicht gefunden")

        if approval.get("status") != "pending":
            raise ValueError("Approval wurde bereits entschieden")

        session_id = str(approval["session_id"])
        run_id = str(approval["run_id"])
        tool_name = str(approval["tool_name"])
        tool_input = dict(approval["tool_input"])
        learned_trigger = self.learning.pop_pending_trigger(run_id)

        if decision == "deny":
            await self.db.resolve_approval(
                approval_id=approval_id,
                status="denied",
                decision="deny",
            )
            denied_text = normalize_honorifics(f"Aktion abgelehnt: {tool_name}. Es wurde nichts ausgefuehrt.")
            await self.db.add_message(session_id=session_id, role="assistant", content=denied_text)
            await self._emit_message(session_id, run_id, denied_text)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="done",
                detail="Freigabe abgelehnt",
            )
            return "denied"

        if decision != "approve":
            raise ValueError("Ungueltige Entscheidung")

        await self.db.resolve_approval(
            approval_id=approval_id,
            status="approved",
            decision="approve",
        )

        await self._emit_state(
            session_id=session_id,
            run_id=run_id,
            state="executing",
            detail=f"Fuehre Tool aus: {tool_name}",
        )

        settings = await self.db.get_settings()
        profile = self._load_profile()

        tool_started_at = time.perf_counter()
        tool_result = await self.tools.execute(
            tool_name=tool_name,
            tool_input=tool_input,
            settings=settings,
            profile=profile,
        )
        tool_latency_ms = int(round((time.perf_counter() - tool_started_at) * 1000))

        await self.db.add_tool_run(
            run_id=run_id,
            session_id=session_id,
            tool_run_id=str(uuid.uuid4()),
            tool_name=tool_name,
            tool_input=tool_input,
            success=tool_result.success,
            result=tool_result.output,
            error=tool_result.error,
        )
        await self.db.record_tool_learning(
            tool_name=tool_name,
            success=tool_result.success,
            latency_ms=tool_latency_ms,
        )
        if learned_trigger:
            await self.db.record_learned_command_result(
                trigger=learned_trigger,
                success=tool_result.success,
            )

        if tool_result.success:
            assistant_text = await self._compose_tool_response(
                settings=settings,
                profile=profile,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output=tool_result.output,
            )
            await self.db.add_message(session_id=session_id, role="assistant", content=assistant_text)
            await self._emit_message(session_id, run_id, assistant_text)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="done",
                detail=f"Tool erfolgreich: {tool_name} ({tool_latency_ms} ms)",
            )
        else:
            error_text = normalize_honorifics(
                f"Tool fehlgeschlagen ({tool_name}): {tool_result.error or 'Unbekannter Fehler'}"
            )
            await self.db.add_message(session_id=session_id, role="assistant", content=error_text)
            await self._emit_message(session_id, run_id, error_text)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="error",
                detail=f"Tool Fehler: {tool_name} ({tool_latency_ms} ms)",
            )

        await maybe_compact_session(self.db, session_id)
        return "approved"

    def start_run_background(self, session_id: str, run_id: str, user_message: str) -> None:
        asyncio.create_task(self.start_run(session_id=session_id, run_id=run_id, user_message=user_message))
