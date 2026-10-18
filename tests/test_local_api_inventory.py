"""Validate planned policy and compare real routes before/after app lifespan."""

import asyncio
from collections import Counter
from contextlib import asynccontextmanager
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field
from starlette.routing import Mount, Route, WebSocketRoute
import pytest


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/security/local-api-route-inventory.json"


class ClosedMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CallerMetadata(ClosedMetadata):
    allowedType: Literal["public_liveness", "authenticated_desktop_main"]
    identitySource: Literal["none", "future_trusted_backend_caller_and_profile_binding"]


class OwnershipMetadata(ClosedMetadata):
    kind: Literal["none", "global_metadata", "profile", "new_session", "session",
                  "owned_session_collection", "approval_session"]
    resourceIdentitySource: Literal["none", "trusted_backend_profile", "server_generated_session_id",
                                    "path.session_id", "body.session_id", "database.approvals.session_id",
                                    "path.approval_id_resolved_server_side"]
    ownerIdentitySource: Literal["not_applicable_liveness", "not_applicable_global_metadata",
                                 "future_backend_profile_caller_binding", "future_session_owner_record",
                                 "database.approvals.session_id_and_future_session_owner_record"]
    requiredCheck: Literal["fixed_liveness_without_authority", "authenticate_profile_caller_without_session_owner",
                            "match_caller_to_backend_profile", "persist_authenticated_caller_and_profile_before_publish",
                            "resolve_session_and_match_caller_and_profile", "filter_approvals_to_owned_sessions_before_return",
                            "resolve_approval_session_owner_before_existing_claim"]
    reason: str = Field(min_length=1)


class RouteMetadata(ClosedMetadata):
    transport: Literal["http", "websocket"]
    methods: list[Literal["GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT"]] = Field(min_length=1)
    path: str = Field(min_length=1)
    handler: str = Field(min_length=1)
    protection: Literal["caller_required", "bootstrap_liveness_only"]
    currentGuard: Literal["none", "origin_only"]
    reason: str = Field(min_length=1)
    policyStage: Literal["future_yjsec_02b"]
    caller: CallerMetadata
    ownership: OwnershipMetadata


def validate_route_policy(row):
    """Test-only schema and explicit route-policy matrix, never a runtime gate."""
    typed = RouteMetadata.model_validate(row)
    assert typed.methods == sorted(set(typed.methods))
    keys = {(typed.transport, method, typed.path) for method in typed.methods}
    public = {("http", "GET", "/health")}
    global_metadata = {("http", method, path) for path in
                       ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc") for method in ("GET", "HEAD")}
    global_metadata.add(("http", "GET", "/v1/setup/models"))
    # Exact entries: adding a route cannot silently inherit a profile permission.
    profile = {("http", method, path) for path, methods in {
        "/v1/settings": ("GET", "PUT"), "/v1/audio/transcribe": ("POST",),
        "/v1/audio/voices": ("GET",), "/v1/audio/speak": ("POST",),
        "/v1/smarthome/entities": ("GET",), "/v1/smarthome/call": ("POST",),
        "/v1/setup/accelerators": ("GET",), "/v1/setup/hardware": ("GET",),
        "/v1/setup/inventory": ("GET",), "/v1/setup/status": ("GET",),
        "/v1/setup/install/options": ("GET",), "/v1/setup/install": ("GET", "POST", "DELETE"),
    }.items() for method in methods}
    special = {
        ("http", "POST", "/v1/sessions"): ("new_session", "server_generated_session_id", "future_session_owner_record", "persist_authenticated_caller_and_profile_before_publish"),
        ("http", "GET", "/v1/sessions/{session_id}/messages"): ("session", "path.session_id", "future_session_owner_record", "resolve_session_and_match_caller_and_profile"),
        ("websocket", "CONNECT", "/v1/ws/{session_id}"): ("session", "path.session_id", "future_session_owner_record", "resolve_session_and_match_caller_and_profile"),
        ("http", "POST", "/v1/chat"): ("session", "body.session_id", "future_session_owner_record", "resolve_session_and_match_caller_and_profile"),
        ("http", "GET", "/v1/approvals/pending"): ("owned_session_collection", "database.approvals.session_id", "database.approvals.session_id_and_future_session_owner_record", "filter_approvals_to_owned_sessions_before_return"),
        ("http", "POST", "/v1/approvals/{approval_id}"): ("approval_session", "path.approval_id_resolved_server_side", "database.approvals.session_id_and_future_session_owner_record", "resolve_approval_session_owner_before_existing_claim"),
    }
    if keys == public:
        assert typed.protection == "bootstrap_liveness_only"
        assert typed.caller.model_dump() == {"allowedType": "public_liveness", "identitySource": "none"}
        expected = ("none", "none", "not_applicable_liveness", "fixed_liveness_without_authority")
    else:
        assert typed.protection == "caller_required"
        assert typed.caller.model_dump() == {"allowedType": "authenticated_desktop_main", "identitySource": "future_trusted_backend_caller_and_profile_binding"}
        if keys <= global_metadata:
            expected = ("global_metadata", "none", "not_applicable_global_metadata", "authenticate_profile_caller_without_session_owner")
        elif keys <= profile:
            expected = ("profile", "trusted_backend_profile", "future_backend_profile_caller_binding", "match_caller_to_backend_profile")
        else:
            assert len(keys) == 1 and next(iter(keys)) in special, "Unreviewed route ownership"
            expected = special[next(iter(keys))]
    owner = typed.ownership
    assert (owner.kind, owner.resourceIdentitySource, owner.ownerIdentitySource, owner.requiredCheck) == expected
    assert typed.reason.strip() and owner.reason.strip()
    return typed


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


async def lifespan_snapshot(app):
    before = collect_routes(app)
    async with app.router.lifespan_context(app):
        after_startup = collect_routes(app)
    return {"before": before, "afterStartup": after_startup,
            "afterShutdown": collect_routes(app), "shutdownCompleted": True}


def test_complete_actual_application_route_inventory(tmp_path):
    # Real import, startup and shutdown only in a disposable process and DB.
    env = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR", "PATH") if name in os.environ}
    env.update({
        "JARVIS_PROJECT_ROOT": str(tmp_path), "JARVIS_RUNTIME_DIR": str(tmp_path / "runtime"),
        "JARVIS_DB_PATH": str(tmp_path / "fixture.db"), "JARVIS_PROFILE_PATH": str(tmp_path / "profile.json"),
        "WHISPER_MODEL": str(tmp_path / "missing.bin"),
        "TEMP": str(tmp_path), "TMP": str(tmp_path),
        "JARVIS_AGENT_HOST": "127.0.0.1", "JARVIS_AGENT_PORT": "0",
    })
    result = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--inventory-worker"],
                            env=env, cwd=tmp_path, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    declared = json.loads(INVENTORY.read_text(encoding="utf-8"))
    assert_inventory(report["routes"], declared["routes"])
    for phase in ("before", "afterStartup", "afterShutdown"):
        assert_inventory(report["lifecycle"][phase], declared["routes"])
    assert report["lifecycle"]["shutdownCompleted"] is True
    assert report["startupEvidence"] == {"temporaryDatabaseInitialized": True, "temporaryProfileCreated": True}
    assert report["pendingTasks"] == report["remainingThreads"] == 0
    assert report["pythonIsolated"] is True
    assert report["guardControls"] == ["network", "dns", "process", "database", "read", "write", "mkdir"]
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
    assert inventory["inventoryVersion"] == 2
    assert inventory["enforcement"] == "planned-only-no-productive-authentication"
    assert set(inventory["syntheticSurfaces"]) == {"corsPreflight", "slashRedirects", "unmatchedRequests"}
    rows = inventory["routes"]
    for row in rows:
        validate_route_policy(row)
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


@pytest.mark.parametrize("hook", ["startup", "lifespan"])
@pytest.mark.parametrize("mutation", ["http", "websocket", "duplicate", "mount"])
def test_inventory_gate_detects_late_registration_and_runs_shutdown(hook, mutation):
    closed = []

    def register(app):
        async def late():
            return {}
        if mutation == "http":
            app.add_api_route("/unreviewed", late, methods=["POST"])
        elif mutation == "websocket":
            app.add_api_websocket_route("/unreviewed", late)
        elif mutation == "duplicate":
            app.routes.append(app.routes[0])
        else:
            app.mount("/unreviewed", FastAPI())

    @asynccontextmanager
    async def lifespan(app):
        register(app)
        try:
            yield
        finally:
            closed.append(True)

    app = FastAPI(lifespan=lifespan) if hook == "lifespan" else FastAPI()
    if hook == "startup":
        app.add_event_handler("startup", lambda: register(app))
        app.add_event_handler("shutdown", lambda: closed.append(True))
    with pytest.raises(AssertionError):
        report = asyncio.run(lifespan_snapshot(app))
        assert_inventory(report["afterStartup"], report["before"])
    assert closed == [True]


@pytest.mark.parametrize("path,method,field,value", [
    ("/health", "GET", "caller", "__delete__"),
    ("/health", "GET", "caller.allowedType", "authenticated_desktop_main"),
    ("/health", "GET", "ownership.kind", "profile"),
    ("/v1/settings", "GET", "caller.allowedType", "public_liveness"),
    ("/v1/settings", "GET", "caller.allowedType", "arbitrary_local_process"),
    ("/v1/settings", "GET", "caller.identitySource", "origin_header"),
    ("/v1/settings", "GET", "caller.extra", True),
    ("/v1/settings", "GET", "policyStage", "already_enforced"),
    ("/v1/settings", "GET", "policyStage", "__delete__"),
    ("/v1/settings", "GET", "ownership.kind", "none"),
    ("/v1/settings", "GET", "ownership.reason", " "),
    ("/v1/settings", "GET", "ownership.extra", True),
    ("/docs", "GET", "ownership.ownerIdentitySource", "future_session_owner_record"),
    ("/v1/setup/models", "GET", "caller.identitySource", "none"),
    ("/v1/sessions", "POST", "ownership.requiredCheck", "resolve_session_and_match_caller_and_profile"),
    ("/v1/sessions", "POST", "ownership.resourceIdentitySource", "body.session_id"),
    ("/v1/sessions", "POST", "ownership.ownerIdentitySource", "__delete__"),
    ("/v1/sessions/{session_id}/messages", "GET", "ownership.ownerIdentitySource", "caller_supplied_owner"),
    ("/v1/sessions/{session_id}/messages", "GET", "ownership.requiredCheck", "match_caller_to_backend_profile"),
    ("/v1/ws/{session_id}", "CONNECT", "ownership.kind", "profile"),
    ("/v1/ws/{session_id}", "CONNECT", "ownership", "__delete__"),
    ("/v1/chat", "POST", "ownership.resourceIdentitySource", "path.session_id"),
    ("/v1/chat", "POST", "ownership.ownerIdentitySource", "not_applicable_global_metadata"),
    ("/v1/approvals/pending", "GET", "ownership.requiredCheck", "authenticate_profile_caller_without_session_owner"),
    ("/v1/approvals/pending", "GET", "ownership.resourceIdentitySource", "none"),
    ("/v1/approvals/{approval_id}", "POST", "ownership.ownerIdentitySource", "future_session_owner_record"),
    ("/v1/approvals/{approval_id}", "POST", "ownership.requiredCheck", "resolve_session_and_match_caller_and_profile"),
    ("/v1/approvals/{approval_id}", "POST", "ownership.resourceIdentitySource", "path.session_id"),
    ("/v1/settings", "GET", "methods", []),
    ("/v1/settings", "GET", "methods", ["GET", "GET"]),
    ("/v1/settings", "GET", "path", "/unreviewed"),
])
def test_invalid_missing_or_contradictory_route_policy_is_rejected(path, method, field, value):
    rows = json.loads(INVENTORY.read_text(encoding="utf-8"))["routes"]
    row = copy.deepcopy(next(r for r in rows if r["path"] == path and method in r["methods"]))
    target = row
    parts = field.split(".")
    for part in parts[:-1]:
        target = target[part]
    if value == "__delete__":
        del target[parts[-1]]
    else:
        target[parts[-1]] = value
    with pytest.raises((ValueError, AssertionError)):
        validate_route_policy(row)


def install_resource_guard(scratch):
    """Constrain Python startup I/O to source/toolchain reads and scratch writes."""
    read_roots = [scratch, ROOT / "apps/agent", Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()]

    def within(value, roots):
        if not isinstance(value, (str, bytes, os.PathLike)):
            return False
        path = Path(os.fsdecode(value)).resolve()
        return any(path.is_relative_to(root) for root in roots)

    def require(value, roots):
        if not within(value, roots):
            raise PermissionError("Inventory worker rejected out-of-scope file access")

    def guard(event, args):
        if event.startswith(("subprocess.", "socket.")) or event in {
            "os.system", "os.posix_spawn", "os.fork", "os.exec", "os.spawn", "os.startfile", "os.startfile/2",
        }:
            raise PermissionError("Inventory worker rejected network/process work")
        if event == "sqlite3.connect":
            require(args[0], [scratch])
        elif event in {"os.listdir", "os.scandir"}:
            require(args[0], read_roots)
        elif event == "open" and not isinstance(args[0], int):
            mode, flags = args[1:]
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            require(args[0], [scratch] if writing else read_roots)
        elif event in {"os.mkdir", "os.rmdir", "os.remove", "os.chmod", "os.truncate"}:
            require(args[0], [scratch])
        elif event == "os.rename":
            require(args[0], [scratch])
            require(args[1], [scratch])
        elif event in {"os.link", "os.symlink"}:
            raise PermissionError("Inventory worker rejected filesystem links")
    sys.addaudithook(guard)


def guard_negative_controls(scratch):
    outside = scratch.parent / "inventory-forbidden"
    controls = [
        ("network", "socket.connect", (None, ("127.0.0.1", 1))),
        ("dns", "socket.getaddrinfo", ("untrusted.invalid", 1, 0, 0, 0)),
        ("process", "subprocess.Popen", ("not-executed", [], None, None)),
        ("database", "sqlite3.connect", (str(outside),)),
        ("read", "open", (str(outside), "r", 0)),
        ("write", "open", (str(outside), "w", os.O_WRONLY | os.O_CREAT)),
        ("mkdir", "os.mkdir", (str(outside), 0o700, -1)),
    ]
    for _name, event, args in controls:
        # Audit-only probes perform no underlying operation, even if the guard
        # regresses. Missing enforcement still fails the test.
        with pytest.raises(PermissionError):
            sys.audit(event, *args)
    return [name for name, _event, _args in controls]


async def inventory_worker():
    # asyncio.run creates its platform event loop before guards are installed;
    # no app code can subsequently create network sockets or child processes.
    scratch = Path.cwd().resolve()
    sys.path.insert(0, str(ROOT / "apps/agent"))
    install_resource_guard(scratch)
    from jarvis_agent.main import app, config, health, setup_installer
    from fastapi.middleware.cors import CORSMiddleware
    import sqlite3
    assert config.project_root == scratch
    assert all(path.is_relative_to(scratch) for path in (config.runtime_dir, config.db_path, config.profile_path, config.default_whisper_model))
    lifecycle = await lifespan_snapshot(app)
    assert setup_installer.task is None and setup_installer.ollama is None
    with sqlite3.connect(config.db_path) as connection:
        seeded = connection.execute("SELECT COUNT(*) FROM settings").fetchone()[0] > 0
        migrated = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] > 0
    return {
        "routes": lifecycle["afterStartup"], "lifecycle": lifecycle, "health": await health(),
        "startupEvidence": {"temporaryDatabaseInitialized": seeded and migrated,
                            "temporaryProfileCreated": config.profile_path.is_file()},
        "pendingTasks": len(asyncio.all_tasks() - {asyncio.current_task()}),
        "pythonIsolated": bool(sys.flags.isolated),
        "guardControls": guard_negative_controls(scratch),
        "cors": [middleware.kwargs for middleware in app.user_middleware if middleware.cls is CORSMiddleware],
        "auth_modules": [name for name in sys.modules if name.startswith("jarvis_agent.caller_auth")],
    }


if __name__ == "__main__" and sys.argv[1:] == ["--inventory-worker"]:
    report = asyncio.run(inventory_worker())
    # asyncio.run joins the DB migration executor. All remaining worker-owned
    # Python threads (including aiosqlite) must also finish before reporting.
    remaining = [thread for thread in threading.enumerate() if thread is not threading.current_thread()]
    for thread in remaining:
        thread.join(timeout=1)
    report["remainingThreads"] = sum(thread.is_alive() for thread in remaining)
    print(json.dumps(report))
