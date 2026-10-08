"""Setup failure/preservation checks without downloads or system installation."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bootstrap_dependencies", ROOT / "setup/install_dependencies.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "checkout with spaces"
    root.mkdir()
    (root / ".python-version").write_text("3.11\n")
    (root / ".nvmrc").write_text("22\n")
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: f"/tools with spaces/{name}")
    return root


def record_commands(monkeypatch, *, node="v22.23.3", venv="3.11", fail=None):
    calls = []

    def fake_run(args, root, *, capture=False):
        calls.append(args)
        if fail and fail(args):
            raise subprocess.CalledProcessError(9, args)
        if "--version" in args:
            return node
        if "-c" in args:
            return venv
        return ""

    monkeypatch.setattr(bootstrap, "run", fake_run)
    return calls


def existing_environment(root):
    environment = root / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_text("existing interpreter")
    marker = environment / "keep.txt"
    marker.write_text("existing environment")
    return marker


def test_wrong_node_aborts_before_creating_environment(project, monkeypatch):
    calls = record_commands(monkeypatch, node="v26.3.1")
    with pytest.raises(RuntimeError, match="Node 22 required"):
        bootstrap.install(project)
    assert len(calls) == 1
    assert not (project / ".venv").exists()


def test_wrong_python_aborts_before_any_command(project, monkeypatch):
    calls = record_commands(monkeypatch)
    monkeypatch.setattr(bootstrap, "sys", SimpleNamespace(
        version_info=SimpleNamespace(major=3, minor=12)))
    with pytest.raises(RuntimeError, match="Python 3.11 required"):
        bootstrap.install(project)
    assert not calls
    assert not (project / ".venv").exists()


def test_missing_npm_aborts_before_any_install(project, monkeypatch):
    calls = record_commands(monkeypatch)
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: None if name.startswith("npm") else "/tools/node")
    with pytest.raises(RuntimeError, match="Node/npm missing"):
        bootstrap.install(project)
    assert not calls
    assert not (project / ".venv").exists()


def test_incompatible_existing_environment_is_preserved(project, monkeypatch):
    marker = existing_environment(project)
    calls = record_commands(monkeypatch, venv="3.12")
    with pytest.raises(RuntimeError, match="left intact"):
        bootstrap.install(project)
    assert marker.read_text() == "existing environment"
    assert len(calls) == 2


def test_incomplete_environment_is_preserved(project, monkeypatch):
    (project / ".venv").mkdir()
    calls = record_commands(monkeypatch)
    with pytest.raises(RuntimeError, match="incomplete"):
        bootstrap.install(project)
    assert len(calls) == 1
    assert (project / ".venv").is_dir()


@pytest.mark.parametrize("failing_step", ["install", "check"])
def test_python_dependency_failure_prevents_npm(project, monkeypatch, failing_step):
    calls = record_commands(monkeypatch, fail=lambda args: "pip" in args and failing_step in args)
    with pytest.raises(subprocess.CalledProcessError):
        bootstrap.install(project)
    assert not any("ci" in args for args in calls)


def test_compatible_environment_is_reused_with_locked_manifests(project, monkeypatch):
    marker = existing_environment(project)
    calls = record_commands(monkeypatch)
    bootstrap.install(project)
    assert marker.read_text() == "existing environment"
    assert not any("venv" in args for args in calls)
    assert calls[-3][1:] == ["-m", "pip", "install", "-r", "apps/agent/requirements.txt",
                             "-r", "requirements-dev.txt"]
    assert calls[-2][1:] == ["-m", "pip", "check"]
    assert calls[-1] == [f"/tools with spaces/{'npm.cmd' if os.name == 'nt' else 'npm'}", "ci"]


def test_npm_failure_is_propagated(project, monkeypatch):
    record_commands(monkeypatch, fail=lambda args: "ci" in args)
    with pytest.raises(subprocess.CalledProcessError):
        bootstrap.install(project)


def test_real_npm_children_find_node_in_a_path_with_spaces(tmp_path, monkeypatch):
    node = shutil.which("node")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert node and npm, "The documented baseline checks require Node/npm"
    root = tmp_path / "npm checkout with spaces"
    root.mkdir()
    (root / "package.json").write_text(json.dumps({
        "name": "setup-probe", "private": True, "scripts": {"probe": "node --version"},
    }))
    # Keep this probe independent of the host's sometimes oversized cmd.exe PATH.
    if os.name == "nt":
        monkeypatch.setenv("PATH", os.pathsep.join([
            str(Path(node).parent), str(Path(npm).parent),
            str(Path(os.environ["SystemRoot"]) / "System32"),
        ]))
    expected = bootstrap.run([node, "--version"], root, capture=True)
    assert expected in bootstrap.run([npm, "run", "probe"], root, capture=True)


def test_native_shell_syntax_and_non_mutating_previews(tmp_path):
    # CI has Bash on Linux and Git Bash + PowerShell on Windows. No installers run.
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = str(git_bash) if os.name == "nt" and git_bash.is_file() else shutil.which("bash")
    assert bash, "Bash is required to validate the POSIX installers"
    target = tmp_path / "checkout with spaces" / "setup"
    target.parent.mkdir()
    shutil.copytree(ROOT / "setup", target)
    for name in ["common.sh", "activate.sh", "macos.sh", "linux.sh"]:
        subprocess.run([bash, "-n", str(target / name)], check=True)
    for name in ["macos.sh", "linux.sh"]:
        result = subprocess.run([bash, str(target / name), "--dry-run"], cwd=tmp_path,
                                check=True, capture_output=True, text=True)
        assert "Keine Modelle" in result.stdout
        assert not (target.parent / ".setup-tools").exists()
        assert not (target.parent / ".venv").exists()
        invalid = subprocess.run([bash, str(target / name), "--unknown"], cwd=tmp_path,
                                 capture_output=True, text=True)
        assert invalid.returncode != 0
    if os.name == "nt":
        powershell = shutil.which("powershell.exe")
        assert powershell, "Windows PowerShell is required to validate the Windows installer"
        for name in ["windows.ps1", "activate.ps1"]:
            # Pass paths as data, including spaces, without interpolating shell code.
            command = "$tokens=$null; $errors=$null; [System.Management.Automation.Language.Parser]::ParseFile($env:YJ_SETUP_PARSE_PATH,[ref]$tokens,[ref]$errors) > $null; if($errors.Count){ $errors; exit 1 }"
            subprocess.run([powershell, "-NoProfile", "-Command", command], check=True,
                           env={**os.environ, "YJ_SETUP_PARSE_PATH": str(target / name)})
        result = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                 str(target / "windows.ps1"), "-DryRun"], cwd=tmp_path,
                                check=True, capture_output=True, text=True)
        assert "Keine Modelle" in result.stdout
        assert not (target.parent / ".setup-tools").exists()
        assert not (target.parent / ".venv").exists()
