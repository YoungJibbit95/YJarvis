from __future__ import annotations

from .generic_provider import GenericProvider, ProviderResult
from ..base import run_command


class MacOSProvider(GenericProvider):
    async def focus_app(self, app_name: str) -> ProviderResult:
        name = str(app_name or "").strip()
        if not name:
            return ProviderResult(success=False, error="app_name fehlt.")
        script = f'tell application "{name}" to activate'
        process = await run_command(["osascript", "-e", script])
        if process.returncode == 0:
            return ProviderResult(success=True, output=f"App fokussiert: {name}")
        return await super().focus_app(name)

    async def list_running_apps(self, limit: int = 40) -> ProviderResult:
        script = (
            'tell application "System Events"\n'
            "set appList to name of (application processes where background only is false)\n"
            "set AppleScript's text item delimiters to linefeed\n"
            "set outText to appList as text\n"
            "set AppleScript's text item delimiters to \"\"\n"
            "return outText\n"
            "end tell"
        )
        process = await run_command(["osascript", "-e", script])
        if process.returncode != 0:
            return await super().list_running_apps(limit=limit)
        lines = [line.strip() for line in (process.stdout or "").splitlines() if line.strip()]
        unique = list(dict.fromkeys(lines))[: max(1, min(int(limit), 200))]
        return ProviderResult(success=True, output="\n".join(unique), data={"apps": unique})

    async def close_app(self, app_name: str) -> ProviderResult:
        name = str(app_name or "").strip()
        if not name:
            return ProviderResult(success=False, error="app_name fehlt.")
        script = f'tell application "{name}" to quit'
        process = await run_command(["osascript", "-e", script])
        if process.returncode == 0:
            return ProviderResult(success=True, output=f"App geschlossen: {name}")
        return await super().close_app(name)
