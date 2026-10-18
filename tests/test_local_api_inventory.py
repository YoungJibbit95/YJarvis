"""Compare the reviewed inventory with real registered routes, without serving."""

from collections import Counter
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

from fastapi import FastAPI
from starlette.routing import Mount, Route, WebSocketRoute
import pytest


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/security/local-api-route-inventory.json"


def collect_routes(app):
    records = []
    for route in app.routes:
        if isinstance(route, WebSocketRoute):
            transport, methods = "websocket", ["CONNECT"]
        elif isinstance(route, Route):
            transport, methods = "http", sorted(route.methods)
        else:
            raise AssertionError("Uninventoried route kind or mounted application")
        records.append({
            "transport": transport, "methods": methods, "path": route.path,
            "handler": route.endpoint.__module__ + "." + route.endpoint.__name__,
        })
    return records


def identities(records):
    return Counter((r["transport"], method, r["path"], r["handler"])
                   for r in records for method in r["methods"])


def assert_inventory(actual, declared):
    assert identities(actual) == identities(declared)


def test_complete_actual_application_route_inventory(tmp_path):
    # Import main only in a disposable process: main has import-time directory
    # setup and service construction. Never import it against personal data.
    env = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR", "PATH") if name in os.environ}
    env.update({
        "PYTHONPATH": str(ROOT / "apps/agent"), "PYTHONDONTWRITEBYTECODE": "1",
        "JARVIS_PROJECT_ROOT": str(tmp_path), "JARVIS_RUNTIME_DIR": str(tmp_path / "runtime"),
        "JARVIS_DB_PATH": str(tmp_path / "fixture.db"), "JARVIS_PROFILE_PATH": str(tmp_path / "profile.json"),
        "WHISPER_MODEL": str(tmp_path / "missing.bin"),
        "TEMP": str(tmp_path), "TMP": str(tmp_path),
    })
    result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--inventory-worker"],
                            env=env, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    declared = json.loads(INVENTORY.read_text(encoding="utf-8"))
    assert_inventory(report["routes"], declared["routes"])
    assert len(declared["routes"]) == 27
    assert sum(len(r["methods"]) for r in declared["routes"]) == 31
    assert report["health"] == {"status": "ok"}
    assert report["cors"] == [{
        "allow_origins": ["app://yjarvis", "http://127.0.0.1:5173", "http://localhost:5173"],
        "allow_credentials": True, "allow_methods": ["*"], "allow_headers": ["*"],
    }]
    assert report["auth_modules"] == []  # No partial activation hidden in imports.


def test_inventory_has_explicit_protection_and_only_minimal_bootstrap_exception():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    assert inventory["enforcement"] == "planned-only-no-productive-authentication"
    assert set(inventory["syntheticSurfaces"]) == {"corsPreflight", "slashRedirects", "unmatchedRequests"}
    rows = inventory["routes"]
    assert all(set(r) == {"transport", "methods", "path", "handler", "protection", "currentGuard", "reason"} for r in rows)
    assert all(r["reason"].strip() and r["methods"] == sorted(set(r["methods"])) for r in rows)
    assert len(identities(rows)) == 31  # Duplicate declarations cannot hide drift.
    public = [r for r in rows if r["protection"] != "caller_required"]
    assert [(r["transport"], r["methods"], r["path"], r["protection"]) for r in public] == [
        ("http", ["GET"], "/health", "bootstrap_liveness_only")]
    guarded = [r for r in rows if r["currentGuard"] != "none"]
    assert {(tuple(r["methods"]), r["path"], r["currentGuard"]) for r in guarded} == {
        (("POST",), "/v1/setup/install", "origin_only"),
        (("DELETE",), "/v1/setup/install", "origin_only"),
    }


@pytest.mark.parametrize("change", ["added", "removed", "method", "handler", "duplicate"])
def test_inventory_gate_detects_route_drift(change):
    expected = json.loads(INVENTORY.read_text(encoding="utf-8"))["routes"]
    actual = copy.deepcopy(expected)
    if change == "added":
        actual.append(dict(actual[0], path="/unreviewed"))
    elif change == "removed":
        actual.pop()
    elif change == "method":
        actual[0]["methods"].append("POST")
    elif change == "handler":
        actual[0]["handler"] = "unreviewed.handler"
    else:
        actual.append(actual[0])
    with pytest.raises(AssertionError):
        assert_inventory(actual, expected)


def test_inventory_gate_rejects_unreviewed_mounts():
    app = FastAPI()
    app.routes.append(Mount("/unreviewed", app=FastAPI()))
    with pytest.raises(AssertionError, match="mounted application"):
        collect_routes(app)


def inventory_worker():
    def guard(event, _args):
        if event.startswith(("subprocess.", "socket.", "sqlite3.connect")) or event == "os.system":
            raise AssertionError("Inventory import attempted external work")
    sys.addaudithook(guard)
    from jarvis_agent.main import app, health
    from fastapi.middleware.cors import CORSMiddleware
    # health has no awaits or side effects; run directly without starting the app.
    coroutine = health()
    try:
        coroutine.send(None)
    except StopIteration as result:
        response = result.value
    finally:
        coroutine.close()
    print(json.dumps({
        "routes": collect_routes(app), "health": response,
        "cors": [middleware.kwargs for middleware in app.user_middleware if middleware.cls is CORSMiddleware],
        "auth_modules": [name for name in sys.modules if name.startswith("jarvis_agent.caller_auth")],
    }))


if __name__ == "__main__" and sys.argv[1:] == ["--inventory-worker"]:
    inventory_worker()
