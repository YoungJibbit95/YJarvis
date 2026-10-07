"""Coordinate the legacy single-tool lifecycle; no routing or OS implementation."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from ..conversation_helpers import normalize_honorifics
from ..db import Database
from ..learning_engine import LearningEngine
from ..memory import maybe_compact_session
from ..tools import ToolRegistry
from .legacy_responses import LegacyResponses
from .legacy_routing import LegacyRouting


class TurnEngine:
    def __init__(
        self,
        db: Database,
        tools: ToolRegistry,
        learning: LearningEngine,
        routing: LegacyRouting,
        responses: LegacyResponses,
        load_profile: Callable[[], dict[str, Any]],
    ) -> None:
        self.db = db
        self.tools = tools
        self.learning = learning
        self.routing = routing
        self.responses = responses
        self._load_profile = load_profile

    async def start_run(self, session_id: str, run_id: str, user_message: str) -> None:
        await self.db.add_message(session_id=session_id, role="user", content=user_message)
        await self.responses.emit_state(
            session_id=session_id, run_id=run_id, state="received", detail="Nachricht empfangen",
        )
        await self.responses.emit_state(
            session_id=session_id, run_id=run_id, state="thinking", detail="Analysiere Anfrage",
        )
        profile = self._load_profile()
        settings = await self.db.get_settings()
        route = await self.routing.route(session_id, run_id, user_message, profile, settings)
        if route.reply is not None:
            await self.responses.finish(session_id, run_id, route.reply, detail=route.detail)
            return

        intent = route.intent
        if intent and self.tools.has_tool(intent.tool_name):
            self.learning.mark_pending_trigger(run_id, intent.source_trigger)
            approval = await self.db.create_approval(
                approval_id=str(uuid.uuid4()),
                session_id=session_id,
                run_id=run_id,
                tool_name=intent.tool_name,
                tool_input=intent.tool_input,
            )
            await self.responses.emit_state(
                session_id=session_id,
                run_id=run_id,
                state="approval_required",
                detail=f"Freigabe erforderlich: {intent.tool_name}",
                data={"approval": approval, "reason": intent.reason},
            )
            return

        await self.responses.stream_response(session_id, run_id, route.user_message, profile, settings)

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
            await self.responses.finish(
                session_id, run_id, denied_text,
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

        await self.responses.emit_state(
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
            assistant_text = await self.responses.compose_tool_response(
                settings=settings,
                profile=profile,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_output=tool_result.output,
            )
            await self.responses.finish(
                session_id, run_id, assistant_text,
                detail=f"Tool erfolgreich: {tool_name} ({tool_latency_ms} ms)",
            )
        else:
            error_text = normalize_honorifics(
                f"Tool fehlgeschlagen ({tool_name}): {tool_result.error or 'Unbekannter Fehler'}"
            )
            await self.responses.finish(
                session_id, run_id, error_text,
                state="error",
                detail=f"Tool Fehler: {tool_name} ({tool_latency_ms} ms)",
            )

        await maybe_compact_session(self.db, session_id)
        return "approved"
