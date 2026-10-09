import asyncio
from unittest.mock import patch

from jarvis_agent.tools.base import ToolContext
from jarvis_agent.tools.capability_tools import ProcessTerminateTool, SchedulerCreateTaskTool
from jarvis_agent.tools.providers import MacOSProvider, WindowsProvider, get_provider


def test_get_provider_returns_windows_provider_when_platform_is_windows():
    with patch("jarvis_agent.tools.providers.platform.system", return_value="Windows"):
        provider = get_provider()
    assert isinstance(provider, WindowsProvider)


def test_get_provider_returns_macos_provider_when_platform_is_darwin():
    with patch("jarvis_agent.tools.providers.platform.system", return_value="Darwin"):
        provider = get_provider()
    assert isinstance(provider, MacOSProvider)


def test_process_terminate_blocks_critical_process_name():
    tool = ProcessTerminateTool()
    result = asyncio.run(
        tool.execute(
            {"name": "systemd", "force": True},
            ToolContext(settings={}),
        )
    )
    assert result.success is False
    assert "Systemkritisch" in (result.error or "")


def test_scheduler_create_task_blocks_dangerous_command():
    tool = SchedulerCreateTaskTool()
    result = asyncio.run(
        tool.execute(
            {"task_name": "wipe", "time": "10:30", "command": "rm -rf /"},
            ToolContext(settings={}),
        )
    )
    assert result.success is False
    assert "blockiert" in (result.error or "")
