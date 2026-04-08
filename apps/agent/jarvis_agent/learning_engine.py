from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

from .conversation_helpers import (
    is_learn_list_request,
    parse_learn_definition_request,
    parse_unlearn_request,
    strip_jarvis_prefix,
    tool_performance_score,
)
from .db import Database
from .tool_intent import ToolCallIntent
from .tools import ToolRegistry


DecideToolIntentFn = Callable[[str, dict[str, Any], bool], Awaitable[ToolCallIntent | None]]


class LearningEngine:
    def __init__(self, db: Database, tools: ToolRegistry) -> None:
        self.db = db
        self.tools = tools
        self.pending_learned_trigger_by_run: dict[str, str] = {}

    def mark_pending_trigger(self, run_id: str, source_trigger: str | None) -> None:
        if source_trigger:
            self.pending_learned_trigger_by_run[run_id] = source_trigger
        else:
            self.pending_learned_trigger_by_run.pop(run_id, None)

    def pop_pending_trigger(self, run_id: str) -> str | None:
        return self.pending_learned_trigger_by_run.pop(run_id, None)

    async def rank_tool_specs_for_planner(self, tool_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not tool_specs:
            return []

        tool_names = [str(spec.get("tool_name", "")).strip() for spec in tool_specs if str(spec.get("tool_name", "")).strip()]
        stats_rows = await self.db.get_tool_learning_stats(tool_names=tool_names)
        stats_by_name = {str(row["tool_name"]): row for row in stats_rows}

        enriched_specs: list[dict[str, Any]] = []
        for spec in tool_specs:
            tool_name = str(spec.get("tool_name", "")).strip()
            stats = stats_by_name.get(tool_name)
            score = tool_performance_score(stats)
            success_count = int(stats.get("success_count", 0)) if stats else 0
            failure_count = int(stats.get("failure_count", 0)) if stats else 0
            runs = success_count + failure_count

            enriched = dict(spec)
            enriched["learned_score"] = round(score, 4)
            enriched["learned_runs"] = runs
            if stats:
                enriched["learned_average_latency_ms"] = int(round(float(stats.get("average_latency_ms", 0.0) or 0.0)))
            enriched_specs.append(enriched)

        enriched_specs.sort(
            key=lambda item: (
                float(item.get("learned_score", 0.0)),
                int(item.get("learned_runs", 0)),
            ),
            reverse=True,
        )
        return enriched_specs

    async def choose_best_tool_candidate(self, candidate_names: list[str]) -> str | None:
        cleaned = [str(item).strip() for item in candidate_names if str(item).strip()]
        if len(cleaned) < 2:
            return cleaned[0] if cleaned else None

        stats_rows = await self.db.get_tool_learning_stats(tool_names=cleaned)
        if not stats_rows:
            return None

        stats_by_name = {str(row["tool_name"]): row for row in stats_rows}
        ranked: list[tuple[str, float, int]] = []
        for name in cleaned:
            stats = stats_by_name.get(name)
            if not stats:
                continue
            runs = int(stats.get("success_count", 0)) + int(stats.get("failure_count", 0))
            if runs < 3:
                continue
            ranked.append((name, tool_performance_score(stats), runs))

        if not ranked:
            return None

        ranked.sort(key=lambda item: (item[1], item[2]), reverse=True)
        best_name, _, _ = ranked[0]
        return best_name

    async def apply_adaptive_routing(self, intent: ToolCallIntent) -> ToolCallIntent:
        tool_name = intent.tool_name
        tool_input = dict(intent.tool_input)

        if tool_name == "open_app":
            app_name = str(tool_input.get("app_name", "")).strip().lower()
            if app_name == "raycast":
                preferred = await self.choose_best_tool_candidate(["open_app", "raycast_open"])
                if preferred == "raycast_open":
                    return ToolCallIntent(
                        tool_name="raycast_open",
                        tool_input={"fallback_text": ""},
                        reason=f"{intent.reason} + adaptives Lernrouting",
                        source_trigger=intent.source_trigger,
                    )

        if tool_name == "raycast_open":
            fallback_text = str(tool_input.get("fallback_text", "")).strip()
            if not fallback_text:
                preferred = await self.choose_best_tool_candidate(["raycast_open", "open_app"])
                if preferred == "open_app":
                    return ToolCallIntent(
                        tool_name="open_app",
                        tool_input={"app_name": "Raycast"},
                        reason=f"{intent.reason} + adaptives Lernrouting",
                        source_trigger=intent.source_trigger,
                    )

        return intent

    async def resolve_learned_command_intent(self, user_message: str) -> ToolCallIntent | None:
        candidate_messages = [user_message]
        stripped = strip_jarvis_prefix(user_message)
        if stripped and stripped != user_message:
            candidate_messages.append(stripped)

        for candidate in candidate_messages:
            learned = await self.db.find_matching_learned_command(candidate)
            if learned is None:
                continue

            tool_name = str(learned.get("tool_name", "")).strip()
            tool_input = learned.get("tool_input", {})
            trigger = str(learned.get("trigger", "")).strip()

            if not tool_name or not isinstance(tool_input, dict):
                continue
            if not self.tools.has_tool(tool_name):
                continue

            return ToolCallIntent(
                tool_name=tool_name,
                tool_input=tool_input,
                reason=f"Gelernter Befehl: {trigger}",
                source_trigger=trigger,
            )

        return None

    async def handle_learning_instruction(
        self,
        *,
        user_message: str,
        settings: dict[str, Any],
        decide_tool_intent: DecideToolIntentFn,
    ) -> str | None:
        if is_learn_list_request(user_message):
            commands = await self.db.list_learned_commands(limit=20)
            if not commands:
                return (
                    "Noch keine Befehle gelernt. Beispiel: "
                    "`/learn \"fokus modus\" => oeffne raycast`."
                )

            lines = ["Gelernte Befehle:"]
            for command in commands[:10]:
                trigger = str(command.get("trigger", ""))
                tool_name = str(command.get("tool_name", ""))
                usage_count = int(command.get("usage_count", 0))
                success_count = int(command.get("success_count", 0))
                failure_count = int(command.get("failure_count", 0))
                total = success_count + failure_count
                success_rate = int(round((success_count / total) * 100)) if total > 0 else 0
                if total > 0:
                    lines.append(
                        f"- `{trigger}` -> `{tool_name}` ({usage_count}x genutzt, {success_rate}% Erfolg)"
                    )
                else:
                    lines.append(f"- `{trigger}` -> `{tool_name}` ({usage_count}x genutzt)")
            return "\n".join(lines)

        trigger_to_forget = parse_unlearn_request(user_message)
        if trigger_to_forget:
            deleted = await self.db.delete_learned_command(trigger_to_forget)
            if deleted:
                return f"Gelerntes Kommando entfernt: `{trigger_to_forget}`."
            return f"Kein gelernter Befehl gefunden fuer `{trigger_to_forget}`."

        learn_definition = parse_learn_definition_request(user_message)
        if learn_definition is None:
            lowered = strip_jarvis_prefix(user_message).lower()
            if re.search(r"\b(?:lern|lerne|teach|beibringen)\b", lowered):
                return (
                    "Bitte im Format: `/learn \"trigger\" => aktion`. "
                    "Beispiel: `/learn \"abendroutine\" => oeffne raycast`."
                )
            return None

        trigger, action_text = learn_definition
        if len(trigger) < 2:
            return "Der Trigger ist zu kurz. Bitte mindestens 2 Zeichen."
        if len(trigger) > 120:
            return "Der Trigger ist zu lang. Bitte maximal 120 Zeichen."

        action_intent = await decide_tool_intent(action_text, settings, False)
        if action_intent is None or not self.tools.has_tool(action_intent.tool_name):
            return (
                "Ich konnte die Aktion nicht eindeutig als Tool-Aufruf erkennen. "
                "Nutzen Sie z. B. `oeffne Safari` oder einen expliziten `/tool` Aufruf."
            )

        await self.db.upsert_learned_command(
            trigger=trigger,
            tool_name=action_intent.tool_name,
            tool_input=action_intent.tool_input,
        )
        return (
            f"Gelernt: `{trigger}` -> `{action_intent.tool_name}`. "
            "Bei Ausfuehrung bleibt die Sicherheitsfreigabe aktiv."
        )

