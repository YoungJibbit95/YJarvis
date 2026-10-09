from __future__ import annotations

from .generic_provider import GenericProvider, ProviderResult
from ..base import run_command


class WindowsProvider(GenericProvider):
    async def focus_app(self, app_name: str) -> ProviderResult:
        name = str(app_name or "").strip()
        if not name:
            return ProviderResult(success=False, error="app_name fehlt.")
        process = await run_command(["powershell", "-NoProfile", "-Command", f"(Get-Process -Name '{name}' -ErrorAction SilentlyContinue | Select-Object -First 1).Id"])
        if process.returncode == 0 and (process.stdout or "").strip():
            return ProviderResult(success=True, output=f"App fokussiert: {name}")
        return await super().focus_app(name)

    async def close_app(self, app_name: str) -> ProviderResult:
        name = str(app_name or "").strip()
        if not name:
            return ProviderResult(success=False, error="app_name fehlt.")
        process = await run_command(["taskkill", "/IM", name, "/T", "/F"])
        if process.returncode == 0:
            return ProviderResult(success=True, output=f"App geschlossen: {name}")
        return await super().close_app(name)
