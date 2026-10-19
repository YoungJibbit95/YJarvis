"""Local, ephemeral credentials only; no route authentication is activated."""

import ast
import base64
from dataclasses import dataclass, FrozenInstanceError, replace
import hashlib
import hmac
import importlib.util
import os
from pathlib import Path
import secrets
import subprocess
import sys

import pytest

from jarvis_agent.caller_auth import core
from jarvis_agent.caller_auth.core import (
    AuthStatus, CredentialVerifier, authenticate,
)


GENERATION = "backend_test_generation"


@dataclass(repr=False)
class Material:
    secret: bytes
    token: str
    verifier: CredentialVerifier


@pytest.fixture
def material():
    # No literal credentials, snapshots, credential files or persisted fixtures.
    secret = secrets.token_bytes(32)
    return Material(secret, base64.urlsafe_b64encode(secret).decode("ascii").rstrip("="),
                    CredentialVerifier.from_secret(secret, caller_id="desktop_main",
                        backend_generation=GENERATION, not_before_ns=100, expires_at_ns=200))


def decide(material, *, presented=None, now=150, verifier=None, generation=GENERATION):
    return authenticate(presented, verifier=verifier or material.verifier,
                        backend_generation=generation, now_ns=now)


def test_only_correct_live_credential_authenticates_the_bound_caller(material):
    decision = decide(material, presented=material.token)
    assert decision.authenticated is True
    assert decision.status is AuthStatus.AUTHENTICATED
    assert decision.caller_id == "desktop_main"
    with pytest.raises(TypeError, match="explicitly"):
        bool(decision)


@pytest.mark.parametrize("now,status", [
    (0, AuthStatus.NOT_YET_VALID), (99, AuthStatus.NOT_YET_VALID),
    (100, AuthStatus.AUTHENTICATED), (199, AuthStatus.AUTHENTICATED),
    (200, AuthStatus.EXPIRED), (201, AuthStatus.EXPIRED),
])
def test_monotonic_lifetime_is_half_open(material, now, status):
    assert decide(material, presented=material.token, now=now).status is status


@pytest.mark.parametrize("now", [None, True, False, -1, 100.0, float("nan"), float("inf"), "150"])
def test_invalid_clock_never_authenticates(material, now):
    assert decide(material, presented=material.token, now=now).status is AuthStatus.INVALID_CONTEXT


@pytest.mark.parametrize("generation", [None, "", True, "bad generation", "g\n", "g" * 129])
def test_invalid_backend_identity_fails_closed(material, generation):
    assert decide(material, presented=material.token, generation=generation).status is AuthStatus.INVALID_CONTEXT


def test_restart_and_revocation_deny_even_the_correct_secret(material):
    assert decide(material, presented=material.token, generation="restarted_backend").status is AuthStatus.WRONG_GENERATION
    revoked = replace(material.verifier, revoked=True)
    assert decide(material, presented=material.token, verifier=revoked).status is AuthStatus.REVOKED
    assert decide(material, presented=material.token, verifier=revoked, now=300).status is AuthStatus.REVOKED
    # A stale verifier snapshot cannot implement live revocation. The future
    # lifecycle owner must supply its current snapshot on every operation.
    assert material.verifier.revoked is False
    with pytest.raises(FrozenInstanceError):
        revoked.revoked = False


def test_wrong_secret_does_not_disclose_record_lifecycle_state(material):
    other = secrets.token_urlsafe(32)
    revoked = replace(material.verifier, revoked=True)
    decision = decide(material, presented=other, verifier=revoked, now=300, generation="other")
    assert decision.status is AuthStatus.INVALID
    assert decision.authenticated is False and decision.caller_id is None


@pytest.mark.parametrize("presented", [None, "", b"", {}, [], True, 123, "127.0.0.1",
    "http://localhost:5173", "app://yjarvis", "Bearer", "a" * 42, "a" * 44, "a" * 1_000_000],
    ids=["missing", "empty", "bytes", "mapping", "list", "bool", "int", "loopback",
         "dev-origin", "app-origin", "scheme-only", "short", "long", "oversized"])
def test_missing_malformed_and_noncredential_inputs_deny(material, presented):
    decision = decide(material, presented=presented)
    assert decision.status is (AuthStatus.MISSING if presented is None else AuthStatus.MALFORMED)
    assert decision.authenticated is False and decision.caller_id is None
    with pytest.raises(TypeError):
        bool(decision)


@pytest.mark.parametrize("alteration", ["space", "newline", "padding", "prefix", "duplicate", "unicode", "pad_bits"])
def test_token_spelling_is_exact_and_unambiguous(material, alteration):
    token = material.token
    variants = {
        "space": " " + token, "newline": token + "\n", "padding": token + "=",
        "prefix": "Bearer " + token, "duplicate": token + "," + token,
        "unicode": token[:-1] + "\u00e9",
    }
    if alteration == "pad_bits":
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        token = token[:-1] + alphabet[alphabet.index(token[-1]) ^ 1]
    else:
        token = variants[alteration]
    assert decide(material, presented=token).status is AuthStatus.MALFORMED


def test_no_configuration_or_untrusted_configuration_never_enables_anonymous_mode(material):
    for presented in (None, material.token):
        decision = authenticate(presented, verifier=None, backend_generation=GENERATION, now_ns=150)
        assert decision.status is AuthStatus.UNCONFIGURED
        assert decision.authenticated is False and decision.caller_id is None
    decision = authenticate(material.token, verifier={}, backend_generation=GENERATION, now_ns=150)
    assert decision.status is AuthStatus.INVALID_CONTEXT


@pytest.mark.parametrize("address", ["127.0.0.1", "::1", "localhost", "192.0.2.1"])
@pytest.mark.parametrize("origin", [None, "app://yjarvis", "http://localhost:5173", "http://127.0.0.1:5173"])
def test_loopback_cors_origin_and_session_metadata_are_not_credentials(material, address, origin):
    # Even internally consistent browser/native transport metadata is untrusted
    # evidence. The core has no argument through which it can grant identity.
    evidence = {"client": address, "origin": origin, "access-control-allow-origin": origin,
                "session_id": "known_session", "host": "127.0.0.1:8787"}
    assert decide(material).status is AuthStatus.MISSING
    assert decide(material, presented=evidence).status is AuthStatus.MALFORMED


def test_secret_comparison_uses_fixed_size_digests(material, monkeypatch):
    called = []
    compare = hmac.compare_digest
    def observed(left, right):
        called.append((type(left), len(left), type(right), len(right)))
        return compare(left, right)
    monkeypatch.setattr(core.hmac, "compare_digest", observed)
    assert decide(material, presented=material.token).authenticated
    assert decide(material, presented=secrets.token_urlsafe(32)).status is AuthStatus.INVALID
    assert called == [(bytes, 32, bytes, 32)] * 2


@pytest.mark.parametrize("change", [
    {"caller_id": ""}, {"backend_generation": "x\n"}, {"digest": b""}, {"digest": "x" * 32},
    {"not_before_ns": -1}, {"not_before_ns": True}, {"expires_at_ns": 100},
    {"expires_at_ns": float("inf")}, {"revoked": 0},
])
def test_malformed_trusted_verifier_cannot_be_created(material, change):
    with pytest.raises(ValueError):
        replace(material.verifier, **change)


@pytest.mark.parametrize("value", [None, "", b"", b"x" * 31, b"x" * 33, bytearray(32)])
def test_factory_rejects_non_fixed_size_material_without_echoing_it(value):
    with pytest.raises(ValueError, match="^Expected 32 bytes of provisioned random material$"):
        CredentialVerifier.from_secret(value, caller_id="c", backend_generation="g", not_before_ns=0, expires_at_ns=1)


def test_results_repr_errors_and_logs_do_not_expose_credential_material(material, caplog, capsys):
    representations = repr(material.verifier) + repr(decide(material, presented=material.token))
    assert material.token not in representations
    assert material.secret.hex() not in representations
    assert material.verifier.digest.hex() not in representations
    assert material.verifier.digest == hashlib.sha256(material.secret).digest()
    assert not caplog.records
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("status", [status for status in AuthStatus if status is not AuthStatus.AUTHENTICATED])
def test_every_denial_has_no_identity_and_cannot_be_used_as_a_truthy_success(status):
    decision = core.AuthDecision(status)
    assert decision.authenticated is False and decision.caller_id is None
    with pytest.raises(TypeError):
        bool(decision)


def test_cold_core_import_and_denial_are_inert(tmp_path):
    script = tmp_path / "inert_core.py"
    script.write_text('''import os
import sys
def guard(event, args):
    if event.startswith(("subprocess.", "socket.", "sqlite3.", "ctypes.")) or event in {
        "os.system", "os.mkdir", "os.remove", "os.rename", "os.putenv", "os.unsetenv"
    }:
        raise AssertionError("Unexpected runtime resource")
    if event == "open":
        mode, flags = args[1:]
        if isinstance(mode, str) and any(c in mode for c in "wax+"):
            raise AssertionError("Unexpected file write")
        if isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise AssertionError("Unexpected file write flags")
sys.addaudithook(guard)
from jarvis_agent.caller_auth.core import authenticate, AuthStatus
decision = authenticate(None, verifier=None, backend_generation="unconfigured", now_ns=0)
assert decision.status is AuthStatus.UNCONFIGURED
assert decision.authenticated is False
assert all(name.startswith("jarvis_agent.caller_auth") for name in sys.modules if name.startswith("jarvis_agent."))
''', encoding="utf-8")
    env = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR", "PATH") if name in os.environ}
    env["PYTHONPATH"] = str(Path(core.__file__).resolve().parents[2])
    result = subprocess.run([sys.executable, "-B", str(script)], env=env, cwd=tmp_path,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_core_is_stdlib_only_and_never_imported_by_product_modules():
    package = Path(core.__file__).parent
    root = package.parent
    for path in root.rglob("*.py"):
        inside = package in path.parents
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                name = node.module or ""
                if node.level:
                    module = ".".join(path.relative_to(root.parent).parts[:-1])
                    name = importlib.util.resolve_name("." * node.level + name, module)
                names = [name, *[name + "." + alias.name for alias in node.names]]
            else:
                continue
            if inside:
                if (path == package / "registry.py" and isinstance(node, ast.ImportFrom)
                        and node.level == 1 and node.module == "core"
                        and {alias.name for alias in node.names} == {
                            "AuthStatus", "CredentialVerifier", "_identifier", "_tick", "authenticate"}):
                    continue  # The sole authorized B1 internal import edge.
                assert all(name.split(".")[0] in sys.stdlib_module_names for name in names), path
            else:
                assert all("caller_auth" not in name.split(".") for name in names), path
