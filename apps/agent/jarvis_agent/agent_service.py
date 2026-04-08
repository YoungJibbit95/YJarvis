from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import Database
from .events import EventBus
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


TOOL_REQUEST_HINTS = (
    "oeffne",
    "starte",
    "launch",
    "reminder",
    "erinnerung",
    "kalender",
    "calendar",
    "clipboard",
    "zwischenablage",
    "copy",
    "paste",
    "read file",
    "write file",
    "datei",
    "url",
    "browser",
    "setze",
    "schreibe",
    "fuehre aus",
    "mach",
)


def _looks_like_tool_request(user_message: str) -> bool:
    lowered = user_message.strip().lower()
    if not lowered:
        return False
    return any(hint in lowered for hint in TOOL_REQUEST_HINTS)


def _normalize_honorifics(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        return normalized

    normalized = re.sub(r"\bmein(?:e|er)?\s+herr(?:n)?\b", "Sir", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bmein(?:e|er)?\s+gebiete?r\b", "Sir", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _quick_local_reply(user_message: str) -> str | None:
    normalized = re.sub(r"\s+", " ", user_message.strip())
    lowered = normalized.lower()
    if not lowered:
        return None

    if len(lowered) > 90:
        return None

    if _looks_like_tool_request(lowered):
        return None

    if re.fullmatch(r"(danke(?: dir)?(?: schoen| schön)?(?: jarvis| sir)?|vielen dank(?:.*)?)", lowered):
        return "Gern, Sir. Soll ich direkt den naechsten Schritt fuer Sie uebernehmen?"

    if re.fullmatch(r"(hallo(?: jarvis)?|hi(?: jarvis)?|hey(?: jarvis)?|guten (?:morgen|tag|abend)(?: jarvis)?)", lowered):
        return "Natuerlich, Sir. Womit kann ich helfen?"

    if re.fullmatch(r"(ok(?:ay)?|passt|perfekt|super|alles klar)", lowered):
        return "Verstanden, Sir."

    return None


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

        system_parts = [
            build_persona_system_prompt(profile),
            "Wenn ein Tool noetig ist, nutze die Tool-Route statt Halluzination.",
            "Antworte standardmaessig kurz und direkt (maximal 4 Saetze), ausser der Nutzer fordert Details.",
        ]

        if memories:
            system_parts.append("Kontext-Erinnerungen:")
            for memory in memories:
                system_parts.append(f"- {memory}")

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
        *,
        user_message: str,
        settings: dict[str, Any],
    ) -> ToolCallIntent | None:
        heuristic_intent = infer_heuristic_tool_call(user_message)
        if heuristic_intent and self.tools.has_tool(heuristic_intent.tool_name):
            return heuristic_intent

        if not self.enable_tool_planner:
            return heuristic_intent

        if not _looks_like_tool_request(user_message):
            return heuristic_intent

        try:
            planned = await plan_tool_call(
                base_url=str(settings.get("ollama_base_url", "http://127.0.0.1:11434")),
                model=str(settings.get("model_name", "qwen2.5:3b-instruct")),
                user_message=user_message,
                tool_specs=self.tools.list_specs(),
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

        return ToolCallIntent(
            tool_name=tool_name,
            tool_input=tool_input,
            reason=reason,
        )

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
                # Bei neuer Nachricht ohne Bestaetigung wird die alte ausstehende Bestätigung verworfen.
                self.pending_confirmations.pop(session_id, None)

        blocked_reason = detect_blocked_user_request(normalized_user_message, profile)
        if blocked_reason:
            blocked_text = _normalize_honorifics(refusal_message(profile, reason=blocked_reason))
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
                ask_text = _normalize_honorifics(confirmation_message(profile, reason=confirm_reason))
                await self.db.add_message(session_id=session_id, role="assistant", content=ask_text)
                await self._emit_message(session_id, run_id, ask_text)
                await self._emit_state(
                    session_id=session_id,
                    run_id=run_id,
                    state="done",
                    detail="Sicherheitsbestaetigung erforderlich",
                )
                return

        quick_reply = _quick_local_reply(normalized_user_message)
        if quick_reply:
            quick_text = _normalize_honorifics(quick_reply)
            await self.db.add_message(session_id=session_id, role="assistant", content=quick_text)
            await self._emit_message(session_id, run_id, quick_text)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="done",
                detail="Schnellantwort lokal",
            )
            return

        intent = await self._decide_tool_intent(
            user_message=normalized_user_message,
            settings=settings,
        )

        if intent and self.tools.has_tool(intent.tool_name):
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

            assistant_text = _normalize_honorifics(assistant_text)
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
            fallback = _normalize_honorifics(f"LLM Fehler: {error}")
            await self.db.add_message(session_id=session_id, role="assistant", content=fallback)
            await self._emit_message(session_id, run_id, fallback)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="error",
                detail="LLM Anfrage fehlgeschlagen",
            )
        except Exception as error:
            fallback = _normalize_honorifics(f"Unerwarteter Fehler: {error}")
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
            return _normalize_honorifics(f"Aktion abgeschlossen ({tool_name}). Ergebnis: {tool_output}")

        try:
            response = await complete_chat(
                base_url=base_url,
                model=model,
                messages=prompt_messages,
                temperature=0.1,
                timeout_seconds=20.0,
            )
            if response.strip():
                return _normalize_honorifics(response)
        except Exception:
            pass

        return _normalize_honorifics(f"Tool `{tool_name}` ausgefuehrt. Ergebnis: {tool_output}")

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

        if decision == "deny":
            await self.db.resolve_approval(
                approval_id=approval_id,
                status="denied",
                decision="deny",
            )
            denied_text = _normalize_honorifics(f"Aktion abgelehnt: {tool_name}. Es wurde nichts ausgefuehrt.")
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

        tool_result = await self.tools.execute(
            tool_name=tool_name,
            tool_input=tool_input,
            settings=settings,
            profile=profile,
        )

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
                detail=f"Tool erfolgreich: {tool_name}",
            )
        else:
            error_text = _normalize_honorifics(
                f"Tool fehlgeschlagen ({tool_name}): {tool_result.error or 'Unbekannter Fehler'}"
            )
            await self.db.add_message(session_id=session_id, role="assistant", content=error_text)
            await self._emit_message(session_id, run_id, error_text)
            await self._emit_state(
                session_id=session_id,
                run_id=run_id,
                state="error",
                detail=f"Tool Fehler: {tool_name}",
            )

        await maybe_compact_session(self.db, session_id)
        return "approved"

    def start_run_background(self, session_id: str, run_id: str, user_message: str) -> None:
        asyncio.create_task(self.start_run(session_id=session_id, run_id=run_id, user_message=user_message))
