import asyncio
from pathlib import Path

from jarvis_agent import native_tools, setup_components


def executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_homebrew_tool_is_found_when_gui_path_is_missing(tmp_path):
    binary = executable(tmp_path / "opt" / "whisper.cpp" / "bin" / "whisper-cli")
    found = native_tools.find_whisper_binary(
        "auto", platform="darwin", env={"PATH": "", "HOMEBREW_PREFIX": str(tmp_path)}
    )
    assert found == str(binary.resolve())


def test_stale_saved_whisper_path_falls_back_to_homebrew(tmp_path):
    binary = executable(tmp_path / "bin" / "whisper-cli")
    found = native_tools.find_whisper_binary(
        str(tmp_path / "removed" / "whisper-cli"),
        platform="darwin",
        env={"PATH": "", "HOMEBREW_PREFIX": str(tmp_path)},
    )
    assert found == str(binary.resolve())


def test_macos_installer_uses_homebrew_formula_and_verifies_binary(monkeypatch):
    calls = []

    class Process:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def spawn(*args, **kwargs):
        calls.append((args, kwargs))
        return Process()

    monkeypatch.setattr(setup_components, "find_system_tool", lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None)
    monkeypatch.setattr(setup_components, "find_whisper_binary", lambda: "/opt/homebrew/bin/whisper-cli")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    progress = []
    result = asyncio.run(setup_components._install_macos_tool("whisper-cli", lambda *args: progress.append(args)))

    assert result == "/opt/homebrew/bin/whisper-cli"
    assert calls[0][0] == ("/opt/homebrew/bin/brew", "install", "whisper.cpp")
    assert calls[0][1]["start_new_session"] is True
    assert calls[0][1]["stdout"] == asyncio.subprocess.DEVNULL
    assert progress == [(0, None)]


def test_install_tool_uses_macos_package_manager_only_when_missing(tmp_path, monkeypatch):
    calls = []

    async def install(name, _progress):
        calls.append(name)
        return "/opt/homebrew/bin/whisper-cli"

    monkeypatch.setattr(setup_components.sys, "platform", "darwin")
    monkeypatch.setattr(setup_components, "existing_tool", lambda *_: None)
    monkeypatch.setattr(setup_components, "_install_macos_tool", install)
    result = asyncio.run(setup_components.install_tool(None, tmp_path, "whisper-cli", lambda *_: None))
    assert result == "/opt/homebrew/bin/whisper-cli"
    assert calls == ["whisper-cli"]
