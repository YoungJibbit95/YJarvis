"""Install the existing project manifests; never import or start the application."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str], root: Path, *, capture: bool = False) -> str:
    result = subprocess.run(
        args, cwd=root, check=True, text=True, env=os.environ.copy(),
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def install(root: Path = ROOT) -> None:
    required_python = (root / ".python-version").read_text().strip()
    required_node = (root / ".nvmrc").read_text().strip()
    current_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    if current_python != required_python:
        raise RuntimeError(f"Python {required_python} required; got {current_python}.")

    node = shutil.which("node")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not node or not npm:
        raise RuntimeError("Node/npm missing. Run the platform setup script first.")
    node_version = run([node, "--version"], root, capture=True)
    if node_version.lstrip("v").split(".")[0] != required_node:
        raise RuntimeError(f"Node {required_node} required; got {node_version}.")

    environment = root / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if environment.exists():
        if not python.is_file():
            raise RuntimeError("Existing .venv is incomplete; inspect it before retrying.")
        version = run([str(python), "-c",
                       "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                      root, capture=True)
        if version != required_python:
            raise RuntimeError(f"Existing .venv uses Python {version}; expected {required_python}. "
                               "It has been left intact. Use a fresh checkout or inspect it manually.")
    else:
        run([sys.executable, "-m", "venv", str(environment)], root)

    run([str(python), "-m", "pip", "install", "-r", "apps/agent/requirements.txt",
         "-r", "requirements-dev.txt"], root)
    run([str(python), "-m", "pip", "check"], root)
    run([npm, "ci"], root)
    print("\nProjektabhaengigkeiten installiert, einschliesslich Piper und Electron.")
    print("Keine Modelle geladen. Danach Setup-Umgebung aktivieren (siehe setup/README.md).")


if __name__ == "__main__":
    try:
        install()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"Setup fehlgeschlagen: {error}", file=sys.stderr)
        sys.exit(1)
