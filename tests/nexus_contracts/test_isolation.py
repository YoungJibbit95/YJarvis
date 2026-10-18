"""Additional isolation gates; existing Domain/Runtime gates stay unchanged."""

import ast
import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "apps" / "agent" / "jarvis_agent"
CONTRACTS = PACKAGE / "nexus_contracts"


def test_contract_imports_are_stdlib_pydantic_jcs_or_contract_local_only():
    for path in CONTRACTS.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                name = node.module or ""
                if node.level:
                    name = importlib.util.resolve_name("." * node.level + name, "jarvis_agent.nexus_contracts")
                names = [name]
            else:
                continue
            for name in names:
                assert (name.split(".")[0] in sys.stdlib_module_names
                        or name in {"pydantic", "rfc8785", "jarvis_agent.nexus_contracts"}
                        or name.startswith("jarvis_agent.nexus_contracts.")), (path, name)


def test_no_product_module_imports_the_contract_package():
    for path in PACKAGE.rglob("*.py"):
        if CONTRACTS in path.parents:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                package = ".".join(path.relative_to(PACKAGE.parent).parts[:-1])
                module = node.module or ""
                if node.level:
                    module = importlib.util.resolve_name("." * node.level + module, package)
                names = [module] + [module + "." + alias.name for alias in node.names]
            else:
                continue
            assert not any("nexus_contracts" in name.split(".") for name in names), path


@pytest.mark.parametrize("attempt", ["none", "process", "socket", "database", "write"])
def test_cold_import_and_dto_validation_do_not_touch_runtime_resources(tmp_path, attempt):
    program = textwrap.dedent("""
        import os
        import sys
        sys.dont_write_bytecode = True
        sys.path.insert(0, sys.argv[1])
        def guard(event, args):
            if event in {"subprocess.Popen", "os.system", "os.posix_spawn",
                         "socket.connect", "socket.bind", "sqlite3.connect",
                         "os.startfile", "os.startfile/2", "os.mkdir", "os.remove",
                         "os.rename"} or event.startswith("ctypes."):
                raise AssertionError("Runtime side effect: " + event)
            if event == "open":
                mode = args[1]
                if isinstance(mode, str) and any(c in mode for c in "wax+"):
                    raise AssertionError("File write")
                if isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                    raise AssertionError("File write flags")
        sys.addaudithook(guard)
        from jarvis_agent.nexus_contracts.validation import validate_contract
        from jarvis_agent.nexus_contracts.constants import METHODS
        assert len(METHODS) == 10
        assert validate_contract("Scope", {"kind": "library"}).valid
        assert validate_contract("RuntimeContext", {
            "instanceId": "i", "rendererEpoch": "r", "runtimeGeneration": "g",
            "sessionId": "s", "bridgeProfileId": "b",
            "account": {"mode": "anonymous-local"}, "scope": {"kind": "library"}
        }).valid
        assert not validate_contract("Scope", {}).valid
        loaded = {name for name in sys.modules if name.startswith("jarvis_agent.")}
        assert all(name.startswith("jarvis_agent.nexus_contracts") for name in loaded), loaded
        # Negative controls prove the guard remains active after validation.
        attempt = sys.argv[2]
        if attempt == "process": sys.audit("subprocess.Popen", "dummy", [], None, None)
        if attempt == "socket": sys.audit("socket.connect", None, ("127.0.0.1", 0))
        if attempt == "database": sys.audit("sqlite3.connect", ":memory:")
        if attempt == "write": open(sys.argv[3], "w")
    """)
    # A script gives dependencies the same __main__.__file__ context as a normal
    # process entry point. The target's audit guard still precedes every import.
    script = tmp_path / "cold_import.py"
    script.write_text(program, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-B", str(script), str(PACKAGE.parent), attempt, str(tmp_path / "forbidden")],
        capture_output=True, text=True, timeout=30,
    )
    if attempt == "none":
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode != 0
        assert "Runtime side effect:" in result.stderr or "File write" in result.stderr
        assert not (tmp_path / "forbidden").exists()
