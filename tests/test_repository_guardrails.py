"""Keep duplicated dependency manifests aligned without importing the application."""

import json
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_python_runtime_dependency_manifests_agree():
    requirements = [
        line.strip()
        for line in (ROOT / "apps/agent/requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    project = tomllib.loads((ROOT / "apps/agent/pyproject.toml").read_text(encoding="utf-8"))
    declared = project["project"]["dependencies"]

    assert len(requirements) == len(set(requirements)), "Duplicate runtime requirements"
    assert len(declared) == len(set(declared)), "Duplicate project dependencies"
    assert set(requirements) == set(declared), "requirements.txt and pyproject.toml have drifted"


def test_npm_lockfile_matches_root_and_workspace_manifests():
    manifest = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    lockfile = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    locked_packages = lockfile["packages"]
    assert locked_packages[""]["workspaces"] == manifest["workspaces"]

    for workspace in ["", *manifest["workspaces"]]:
        package = json.loads((ROOT / workspace / "package.json").read_text(encoding="utf-8"))
        locked = locked_packages[workspace]
        for field in ("name", "version"):
            assert locked.get(field) == package.get(field), f"{workspace or 'root'}: {field} drift"
        for field in ("dependencies", "devDependencies", "optionalDependencies"):
            assert locked.get(field, {}) == package.get(field, {}), (
                f"{workspace or 'root'}: {field} differs from package-lock.json; regenerate the lockfile"
            )
