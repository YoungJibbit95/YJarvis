import asyncio
from pathlib import Path

from jarvis_agent.agent_service import AgentService
from jarvis_agent.events import EventBus
from jarvis_agent.tools import ToolRegistry


class _SettingsOnlyDb:
    def __init__(self) -> None:
        self.calls = 0

    async def get_settings(self):
        self.calls += 1
        return {"model_name": "qwen2.5:7b-instruct", "ollama_base_url": "http://127.0.0.1:11434"}


def test_agent_service_settings_cache_and_invalidation():
    async def _run() -> None:
        db = _SettingsOnlyDb()
        service = AgentService(
            db=db,  # type: ignore[arg-type]
            event_bus=EventBus(),
            tools=ToolRegistry(),
            profile_path=Path("/tmp/jarvis-profile-test.json"),
        )

        first = await service._get_settings()
        second = await service._get_settings()
        assert first["model_name"] == "qwen2.5:7b-instruct"
        assert second["model_name"] == "qwen2.5:7b-instruct"
        assert db.calls == 1

        service.invalidate_settings_cache()
        third = await service._get_settings()
        assert third["model_name"] == "qwen2.5:7b-instruct"
        assert db.calls == 2

    asyncio.run(_run())
