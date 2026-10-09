"""Discovery helpers for native tools installed outside the project runtime."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


_HOMEBREW_FORMULAE = {
    "whisper-cli": ("whisper.cpp", "whisper-cpp"),
    "whisper-cpp": ("whisper.cpp", "whisper-cpp"),
    "ffmpeg": ("ffmpeg",),
}


def _executable(path: Path) -> str | None:
    try:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
    except (OSError, RuntimeError):
        pass
    return None


def find_system_tool(name: str, *, platform: str | None = None,
                     env: dict[str, str] | None = None) -> str | None:
    """Find a command from PATH or stable Homebrew links, including GUI apps."""
    host = platform or sys.platform
    environment = os.environ if env is None else env
    resolved = shutil.which(name, path=environment.get("PATH"))
    if resolved:
        return resolved
    if host != "darwin":
        return None

    prefixes = []
    configured_prefix = environment.get("HOMEBREW_PREFIX")
    if configured_prefix:
        prefixes.append(Path(configured_prefix).expanduser())
    prefixes.extend((Path("/opt/homebrew"), Path("/usr/local")))
    formulae = _HOMEBREW_FORMULAE.get(name, ())
    candidates = []
    for prefix in dict.fromkeys(prefixes):
        candidates.append(prefix / "bin" / name)
        for formula in formulae:
            candidates.append(prefix / "opt" / formula / "bin" / name)
    for candidate in candidates:
        found = _executable(candidate)
        if found:
            return found
    return None


def find_whisper_binary(configured: str = "auto", *, platform: str | None = None,
                        env: dict[str, str] | None = None) -> str | None:
    """Resolve a saved Whisper command, falling back to installed CLI aliases."""
    value = str(configured or "auto").strip()
    if value.lower() != "auto":
        explicit_path = Path(value).expanduser()
        if explicit_path.is_absolute() or explicit_path.parent != Path("."):
            found = _executable(explicit_path)
            if found:
                return found
        else:
            found = find_system_tool(value, platform=platform, env=env)
            if found:
                return found
    for candidate in ("whisper-cli", "whisper-cpp"):
        found = find_system_tool(candidate, platform=platform, env=env)
        if found:
            return found
    return None
