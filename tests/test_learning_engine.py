import asyncio

from jarvis_agent.learning_engine import LearningEngine
from jarvis_agent.tool_intent import ToolCallIntent


class _DummyDb:
    async def get_tool_learning_stats(self, tool_names=None):
        return []


class _DummyTools:
    def __init__(self, names: set[str]) -> None:
        self._names = names

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._names


def test_infer_followup_intent_for_multistep_open_app():
    engine = LearningEngine(
        db=_DummyDb(),
        tools=_DummyTools({"open_app", "notes_create"}),
    )
    primary = ToolCallIntent(
        tool_name="open_app",
        tool_input={"app_name": "Notes"},
        reason="App oeffnen erkannt",
    )

    followup = asyncio.run(
        engine.infer_followup_intent_for_multistep(
            user_message="Jarvis, oeffne Notizen und erstelle eine Notiz mit Titel Einkaufsliste",
            primary_intent=primary,
        )
    )

    assert followup is not None
    assert followup.tool_name == "notes_create"
    assert "Folgeschritt" in followup.reason


def test_suggest_recovery_intent_for_raycast_command_failure():
    engine = LearningEngine(
        db=_DummyDb(),
        tools=_DummyTools({"raycast_open", "raycast_run_command"}),
    )

    recovery = asyncio.run(
        engine.suggest_recovery_intent(
            user_message="Jarvis, suche datei roadmap in raycast",
            attempted_tool_name="raycast_run_command",
            attempted_tool_input={"fallback_text": "roadmap"},
            error_message="Raycast Deeplink fehlgeschlagen",
        )
    )

    assert recovery is not None
    assert recovery.tool_name == "raycast_open"
    assert recovery.tool_input["fallback_text"] == "roadmap"
