from __future__ import annotations

import platform

from .generic_provider import GenericProvider, ProviderResult
from .macos_provider import MacOSProvider
from .windows_provider import WindowsProvider


def get_provider() -> GenericProvider:
    system_name = platform.system().lower()
    if system_name == "darwin":
        return MacOSProvider()
    if system_name == "windows":
        return WindowsProvider()
    return GenericProvider()


__all__ = ["GenericProvider", "ProviderResult", "MacOSProvider", "WindowsProvider", "get_provider"]
