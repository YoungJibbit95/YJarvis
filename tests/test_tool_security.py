from pathlib import Path

from jarvis_agent.tools.security import is_path_allowed, resolve_path


def test_path_inside_allowlist_is_allowed(tmp_path: Path):
    allowed = tmp_path / "workspace"
    target = allowed / "nested" / "file.txt"

    assert is_path_allowed(target.resolve(), [str(allowed.resolve())])


def test_path_outside_allowlist_is_blocked(tmp_path: Path):
    allowed = tmp_path / "workspace"
    target = tmp_path / "other" / "file.txt"

    assert not is_path_allowed(target.resolve(), [str(allowed.resolve())])


def test_resolve_path_expands_home(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    resolved = resolve_path("~/abc")

    assert str(resolved).startswith(str(tmp_path))
