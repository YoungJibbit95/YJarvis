"""Compatibility entry point and composition for the existing FastAPI callers."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from .db import Database
from .events import EventBus
from .learning_engine import LearningEngine
from .orchestration.legacy_responses import LegacyResponses
from .orchestration.legacy_routing import LegacyRouting
from .orchestration.turn_engine import TurnEngine
from .profile import load_profile
from .tools import ToolRegistry


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

        history_limit = max(3, int(os.environ.get("JARVIS_HISTORY_LIMIT", "6")))
        memory_limit = max(1, int(os.environ.get("JARVIS_MEMORY_LIMIT", "1")))
        enable_tool_planner = (
            os.environ.get("JARVIS_ENABLE_TOOL_PLANNER", "0").strip().lower() in {"1", "true", "yes", "on"}
        )
        enable_llm_tool_summary = (
            os.environ.get("JARVIS_TOOL_SUMMARY_VIA_LLM", "0").strip().lower() in {"1", "true", "yes", "on"}
        )
        token_flush_interval_seconds = max(
            0.01,
            float(os.environ.get("JARVIS_TOKEN_FLUSH_INTERVAL_MS", "20")) / 1000.0,
        )
        token_flush_min_chars = max(
            1,
            int(os.environ.get("JARVIS_TOKEN_FLUSH_MIN_CHARS", "8")),
        )
        responses = LegacyResponses(
            db, event_bus,
            history_limit=history_limit,
            memory_limit=memory_limit,
            enable_llm_tool_summary=enable_llm_tool_summary,
            token_flush_interval_seconds=token_flush_interval_seconds,
            token_flush_min_chars=token_flush_min_chars,
        )
        routing = LegacyRouting(tools, self.learning, responses, enable_tool_planner=enable_tool_planner)
        self.pending_confirmations = routing.pending_confirmations
        self.turn_engine = TurnEngine(db, tools, self.learning, routing, responses, self._load_profile)

    def _load_profile(self) -> dict[str, Any]:
        return load_profile(self.profile_path)

    async def start_run(self, session_id: str, run_id: str, user_message: str) -> None:
        await self.turn_engine.start_run(session_id, run_id, user_message)

    async def handle_approval_decision(self, approval_id: str, decision: str) -> str:
        return await self.turn_engine.handle_approval_decision(approval_id, decision)

    def start_run_background(self, session_id: str, run_id: str, user_message: str) -> None:
        asyncio.create_task(self.start_run(session_id=session_id, run_id=run_id, user_message=user_message))
