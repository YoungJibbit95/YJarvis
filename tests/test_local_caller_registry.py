"""Ephemeral registry lifecycle tests; no transport or persistence claim."""

import ast
import base64
from concurrent.futures import ThreadPoolExecutor
import copy
from dataclasses import asdict, dataclass, FrozenInstanceError, replace
import os
from pathlib import Path
import pickle
import secrets
import subprocess
import sys
from threading import Barrier, Event, Thread

import pytest

from jarvis_agent.caller_auth import registry as module
from jarvis_agent.caller_auth.core import AuthStatus, CredentialVerifier
from jarvis_agent.caller_auth.registry import (
    CallerContext, CredentialRegistry, RegistryDenial, RegistryState,
)


GENERATION = "backend_generation"
PROFILE = "security_profile"
CALLER = "desktop_main"


class Clock:
    value = 150

    def __call__(self):
        return self.value


@dataclass(repr=False)
class Material:
    token: str
    verifier: CredentialVerifier


def material(**changes):
    secret = secrets.token_bytes(32)
    verifier = CredentialVerifier.from_secret(secret, caller_id=CALLER,
        backend_generation=GENERATION, not_before_ns=100, expires_at_ns=200)
    return Material(base64.urlsafe_b64encode(secret).decode("ascii").rstrip("="),
                    replace(verifier, **changes))


@pytest.fixture
def setup():
    clock = Clock()
    registry = CredentialRegistry(backend_generation=GENERATION, profile_id=PROFILE, clock_ns=clock)
    return registry, clock, material()


def installed(setup):
    registry, clock, first = setup
    registry.install(first.verifier, profile_id=PROFILE)
    return registry, clock, first


def test_empty_registry_denies_without_anonymous_fallback(setup):
    registry, _, first = setup
    for token in (None, first.token):
        result = registry.authenticate(token)
        assert result.status is AuthStatus.UNCONFIGURED
        assert result.authenticated is False and result.context is None
    snapshot = registry.snapshot()
    assert snapshot.state is RegistryState.EMPTY and snapshot.epoch == 0


def test_success_binds_only_trusted_identity_and_has_no_implicit_truthiness(setup):
    registry, _, first = installed(setup)
    result = registry.authenticate(first.token)
    assert result.authenticated is True
    context = result.context
    assert (context.caller_id, context.profile_id, context.backend_generation, context.epoch) == (
        CALLER, PROFILE, GENERATION, 1)
    checked = registry.check_context(context)
    assert checked.authenticated is True
    for value in (result, context):
        with pytest.raises(TypeError, match="explicitly"):
            bool(value)
    with pytest.raises(FrozenInstanceError):
        context.epoch = 2


@pytest.mark.parametrize("change", [
    {"caller_id": "other"}, {"profile_id": "other"}, {"backend_generation": "other"},
    {"epoch": 0}, {"epoch": True}, {"caller_id": None}, {"profile_id": 1},
    {"_registry_tag": object()},
], ids=["caller", "profile", "generation", "epoch", "bool-epoch", "null-caller", "int-profile", "tag"])
def test_altered_context_is_not_authority(setup, change):
    registry, _, first = installed(setup)
    context = registry.authenticate(first.token).context
    result = registry.check_context(replace(context, **change))
    assert result.status is RegistryDenial.STALE_CONTEXT and result.context is None


@pytest.mark.parametrize("value", [None, {}, [], True, 1, "context"])
def test_non_context_inputs_deny(setup, value):
    registry, _, _ = installed(setup)
    result = registry.check_context(value)
    assert result.authenticated is False and result.context is None


@pytest.mark.parametrize("now,status", [(99, AuthStatus.NOT_YET_VALID),
    (100, AuthStatus.AUTHENTICATED), (199, AuthStatus.AUTHENTICATED),
    (200, AuthStatus.EXPIRED), (201, AuthStatus.EXPIRED)])
def test_half_open_lifetime_uses_only_injected_monotonic_clock(setup, now, status):
    registry, clock, first = setup
    clock.value = 0
    registry.install(first.verifier, profile_id=PROFILE)
    clock.value = now
    result = registry.authenticate(first.token)
    assert result.status is status


def test_expired_context_cannot_be_reactivated_by_clock_rollback(setup):
    registry, clock, first = installed(setup)
    context = registry.authenticate(first.token).context
    clock.value = 200
    result = registry.check_context(context)
    assert result.status is AuthStatus.EXPIRED
    clock.value = 150
    result = registry.authenticate(first.token)
    assert result.status is AuthStatus.INVALID_CONTEXT
    clock.value = 201
    assert registry.snapshot().state is RegistryState.FAULTED
    with pytest.raises(ValueError):
        registry.rotate(material(expires_at_ns=300).verifier, profile_id=PROFILE, expected_epoch=1)


@pytest.mark.parametrize("value", [None, True, False, -1, 1.0, float("nan"), float("inf"), "150"])
def test_invalid_clock_is_terminal_and_never_echoed(setup, value):
    registry, clock, first = installed(setup)
    clock.value = value
    result = registry.authenticate(first.token)
    assert result.status is AuthStatus.INVALID_CONTEXT
    clock.value = 150
    result = registry.authenticate(first.token)
    assert result.status is AuthStatus.INVALID_CONTEXT
    with pytest.raises(ValueError, match="^Registry rotation rejected$"):
        registry.rotate(material().verifier, profile_id=PROFILE, expected_epoch=1)


def test_clock_exception_does_not_escape_or_leak_and_permanently_denies():
    first = material()
    class FailingClock:
        def __call__(self):
            raise RuntimeError(first.token)
    registry = CredentialRegistry(backend_generation=GENERATION, profile_id=PROFILE,
                                  clock_ns=FailingClock())
    with pytest.raises(ValueError, match="^Registry cannot accept initial registration$") as caught:
        registry.install(first.verifier, profile_id=PROFILE)
    assert caught.value.__context__ is None
    assert registry.snapshot().state is RegistryState.FAULTED


@pytest.mark.parametrize("change", [
    {"backend_generation": ""}, {"backend_generation": None}, {"backend_generation": True},
    {"backend_generation": "a" * 129}, {"profile_id": "p\n"}, {"profile_id": 1},
    {"profile_id": ""}, {"clock_ns": None}, {"clock_ns": 150},
])
def test_invalid_constructor_rejected_without_values(change):
    config = dict(backend_generation=GENERATION, profile_id=PROFILE, clock_ns=Clock())
    config.update(change)
    with pytest.raises(ValueError, match="^Invalid registry configuration$"):
        CredentialRegistry(**config)


@pytest.mark.parametrize("phase", ["install", "rotate"])
@pytest.mark.parametrize("fault", ["profile", "profile-type", "generation", "verifier-type", "revoked", "expired"])
def test_invalid_registration_never_changes_accepted_binding(setup, phase, fault):
    registry, _, first = setup
    if phase == "rotate":
        registry.install(first.verifier, profile_id=PROFILE)
    record, profile = material().verifier, PROFILE
    if fault == "profile":
        profile = "other"
    elif fault == "profile-type":
        profile = True
    elif fault == "generation":
        record = replace(record, backend_generation="previous_generation")
    elif fault == "verifier-type":
        record = {}
    elif fault == "revoked":
        record = replace(record, revoked=True)
    elif fault == "expired":
        record = replace(record, expires_at_ns=150)
    before = registry.snapshot()
    with pytest.raises(ValueError):
        if phase == "install":
            registry.install(record, profile_id=profile)
        else:
            registry.rotate(record, profile_id=profile, expected_epoch=before.epoch)
    assert registry.snapshot() == before


def test_duplicate_install_and_switching_caller_are_rejected(setup):
    registry, _, first = installed(setup)
    with pytest.raises(ValueError):
        registry.install(material().verifier, profile_id=PROFILE)
    with pytest.raises(ValueError, match="^Invalid registry binding$"):
        registry.rotate(material(caller_id="other").verifier, profile_id=PROFILE, expected_epoch=1)
    result = registry.authenticate(first.token)
    assert result.authenticated is True and result.context.caller_id == CALLER


@pytest.mark.parametrize("epoch", [None, True, False, -1, 0, 2, 1.0, "1"])
def test_rotation_requires_exact_current_epoch(setup, epoch):
    registry, _, _ = installed(setup)
    before = registry.snapshot()
    with pytest.raises(ValueError, match="^Registry rotation rejected$"):
        registry.rotate(material().verifier, profile_id=PROFILE, expected_epoch=epoch)
    assert registry.snapshot() == before


def test_rotation_retires_old_tokens_contexts_and_all_prior_records(setup):
    registry, _, first = installed(setup)
    context = registry.authenticate(first.token).context
    snapshot = registry.snapshot()
    second = material()
    rotated = registry.rotate(second.verifier, profile_id=PROFILE, expected_epoch=snapshot.epoch)
    assert rotated.epoch == 2 and snapshot.epoch == 1
    result = registry.authenticate(first.token)
    assert result.status is AuthStatus.INVALID
    result = registry.check_context(context)
    assert result.status is RegistryDenial.STALE_CONTEXT
    result = registry.authenticate(second.token)
    assert result.authenticated is True and result.context.epoch == 2
    for old in (first.verifier, second.verifier, replace(first.verifier, expires_at_ns=500)):
        with pytest.raises(ValueError, match="^Credential record cannot be installed$"):
            registry.rotate(old, profile_id=PROFILE, expected_epoch=2)
    with pytest.raises(ValueError):
        registry.rotate(material().verifier, profile_id=PROFILE, expected_epoch=snapshot.epoch)


def test_revoke_is_idempotent_and_stale_records_never_undo_it(setup):
    registry, _, first = installed(setup)
    context = registry.authenticate(first.token).context
    snapshot = registry.snapshot()
    revoked = registry.revoke()
    assert registry.revoke() == revoked and revoked.epoch == snapshot.epoch + 1
    result = registry.authenticate(first.token)
    assert result.status is AuthStatus.REVOKED
    result = registry.check_context(context)
    assert result.authenticated is False
    result = registry.authenticate(material().token)
    assert result.status is AuthStatus.INVALID  # Preserve core diagnostic precedence.
    with pytest.raises(ValueError):
        registry.rotate(first.verifier, profile_id=PROFILE, expected_epoch=revoked.epoch)
    fresh = material()
    registry.rotate(fresh.verifier, profile_id=PROFILE, expected_epoch=revoked.epoch)
    result = registry.authenticate(fresh.token)
    assert result.authenticated is True
    result = registry.check_context(context)
    assert result.authenticated is False


def test_expiry_allows_only_explicit_rotation_to_fresh_material(setup):
    registry, clock, first = installed(setup)
    clock.value = 200
    snapshot = registry.snapshot()
    assert snapshot.state is RegistryState.EXPIRED
    with pytest.raises(ValueError):
        registry.rotate(replace(first.verifier, expires_at_ns=300), profile_id=PROFILE,
                        expected_epoch=snapshot.epoch)
    fresh = material(not_before_ns=200, expires_at_ns=300)
    registry.rotate(fresh.verifier, profile_id=PROFILE, expected_epoch=snapshot.epoch)
    result = registry.authenticate(fresh.token)
    assert result.authenticated is True


@pytest.mark.parametrize("configured", [False, True])
def test_close_is_terminal_including_old_context_and_fresh_install(setup, configured):
    registry, _, first = setup
    context = None
    if configured:
        registry.install(first.verifier, profile_id=PROFILE)
        context = registry.authenticate(first.token).context
    closed = registry.close()
    assert registry.close() == closed and registry.revoke() == closed
    for result in (registry.authenticate(first.token), registry.check_context(context)):
        assert result.status is RegistryDenial.CLOSED and result.context is None
    for operation in (lambda: registry.install(first.verifier, profile_id=PROFILE),
                      lambda: registry.rotate(material().verifier, profile_id=PROFILE, expected_epoch=closed.epoch)):
        with pytest.raises(ValueError):
            operation()


def test_generation_change_requires_empty_new_registry_and_new_verifier(setup):
    registry, clock, first = installed(setup)
    context = registry.authenticate(first.token).context
    registry.close()
    restarted = CredentialRegistry(backend_generation="new_generation", profile_id=PROFILE, clock_ns=clock)
    with pytest.raises(ValueError):
        restarted.install(first.verifier, profile_id=PROFILE)
    fresh = material(backend_generation="new_generation")
    restarted.install(fresh.verifier, profile_id=PROFILE)
    result = restarted.authenticate(first.token)
    assert result.authenticated is False
    result = restarted.check_context(context)
    assert result.authenticated is False


def test_contexts_are_not_transferable_even_between_identical_registry_bindings(setup):
    registry, clock, first = installed(setup)
    context = registry.authenticate(first.token).context
    other = CredentialRegistry(backend_generation=GENERATION, profile_id=PROFILE, clock_ns=clock)
    other.install(first.verifier, profile_id=PROFILE)
    result = other.check_context(context)
    assert result.status is RegistryDenial.STALE_CONTEXT
    fabricated = CallerContext(CALLER, PROFILE, GENERATION, 1, object())
    result = other.check_context(fabricated)
    assert result.authenticated is False


@pytest.mark.parametrize("value,status", [(None, AuthStatus.MISSING), (True, AuthStatus.MALFORMED),
    (1, AuthStatus.MALFORMED), ({}, AuthStatus.MALFORMED), (b"", AuthStatus.MALFORMED),
    ("", AuthStatus.MALFORMED), ("127.0.0.1", AuthStatus.MALFORMED),
    ("app://yjarvis", AuthStatus.MALFORMED)])
def test_missing_invalid_and_transport_metadata_are_not_credentials(setup, value, status):
    registry, _, _ = installed(setup)
    result = registry.authenticate(value)
    assert result.status is status and result.context is None
    with pytest.raises(TypeError):
        bool(result)


def test_multiple_readers_observe_consistent_public_snapshots(setup):
    registry, _, first = installed(setup)
    barrier = Barrier(8)
    def read():
        barrier.wait(timeout=10)
        return [(registry.snapshot(), registry.authenticate(first.token)) for _ in range(25)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: read(), range(8)))
    for batch in results:
        for snapshot, result in batch:
            assert snapshot.epoch == 1 and snapshot.state is RegistryState.CONFIGURED
            assert result.authenticated is True
            assert (result.context.caller_id, result.context.profile_id,
                    result.context.backend_generation, result.context.epoch) == (CALLER, PROFILE, GENERATION, 1)


@pytest.mark.parametrize("transition", ["revoke", "rotate", "close"])
def test_transition_cannot_interleave_with_a_verification_holding_the_lock(setup, transition):
    registry, clock, first = installed(setup)
    entered, release, attempted, finished = Event(), Event(), Event(), Event()
    results = []
    fresh = material()
    class BlockingClock:
        def __call__(self):
            entered.set()
            if not release.wait(timeout=10):
                raise RuntimeError("test synchronization timeout")
            return clock.value
    registry._clock = BlockingClock()
    def read():
        results.append(registry.authenticate(first.token))
    def change():
        attempted.set()
        if transition == "rotate":
            results.append(registry.rotate(fresh.verifier, profile_id=PROFILE, expected_epoch=1))
        else:
            results.append(getattr(registry, transition)())
        finished.set()
    reader, writer = Thread(target=read), Thread(target=change)
    reader.start()
    try:
        assert entered.wait(timeout=10)
        writer.start()
        assert attempted.wait(timeout=10)
        assert not finished.wait(timeout=0.05)
    finally:
        release.set()
        reader.join(timeout=10)
        if writer.ident is not None:
            writer.join(timeout=10)
    assert not reader.is_alive() and not writer.is_alive() and finished.is_set()
    assert results[0].authenticated is True and results[0].context.epoch == 1
    result = registry.check_context(results[0].context)
    assert result.authenticated is False
    result = registry.authenticate(first.token)
    assert result.authenticated is False
    if transition == "rotate":
        result = registry.authenticate(fresh.token)
        assert result.authenticated is True and result.context.epoch == 2


def test_simultaneous_rotations_have_one_cas_winner_and_retire_old_token(setup):
    registry, _, first = installed(setup)
    barrier = Barrier(8)
    def rotate(_):
        fresh = material()
        barrier.wait(timeout=10)
        try:
            snapshot = registry.rotate(fresh.verifier, profile_id=PROFILE, expected_epoch=1)
            return snapshot.epoch
        except ValueError:
            return 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        epochs = list(pool.map(rotate, range(8)))
    assert sorted(epochs) == [0] * 7 + [2]
    result = registry.authenticate(first.token)
    assert result.status is AuthStatus.INVALID


@pytest.mark.parametrize("operation", [copy.copy, copy.deepcopy, pickle.dumps], ids=["copy", "deepcopy", "pickle"])
def test_registry_cannot_be_cloned_or_persisted(setup, operation):
    registry, _, _ = installed(setup)
    with pytest.raises(TypeError):
        operation(registry)


def test_public_results_never_contain_secrets_or_digests(setup, caplog, capsys):
    registry, _, first = installed(setup)
    result = registry.authenticate(first.token)
    text = repr(registry) + repr(result) + repr(registry.snapshot())
    text += repr(asdict(result)) + repr(asdict(registry.snapshot()))
    assert first.token not in text
    assert repr(first.verifier.digest) not in text and first.verifier.digest.hex() not in text
    with pytest.raises(ValueError) as caught:
        registry.rotate(first.verifier, profile_id=PROFILE, expected_epoch=1)
    assert first.token not in str(caught.value) and repr(first.verifier.digest) not in str(caught.value)
    assert not caplog.records
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_registry_imports_only_stdlib_and_the_exact_core_edge():
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert all(isinstance(node, ast.ImportFrom) for node in imports)
    assert {(node.level, node.module) for node in imports} == {
        (0, "collections.abc"), (0, "dataclasses"), (0, "enum"), (0, "threading"), (1, "core")}
    root = Path(module.__file__).resolve().parents[4]
    for folder in (root / "scripts", root / "packaging", root / "apps/desktop/electron",
                   root / "apps/desktop/src"):
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".cjs", ".mjs", ".ts", ".tsx", ".spec"}:
                assert "caller_auth" not in path.read_text(encoding="utf-8"), str(path.relative_to(root))


def test_cold_import_and_full_registry_lifecycle_do_no_io_or_background_work(tmp_path):
    script = tmp_path / "inert_registry.py"
    script.write_text('''import base64
import os
import secrets
import sys
import threading
secret = secrets.token_bytes(32)
replacement = secrets.token_bytes(32)
def forbidden(*args, **kwargs):
    raise AssertionError("Unexpected background work")
threading.Thread.start = forbidden
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
from jarvis_agent.caller_auth.registry import CredentialRegistry
from jarvis_agent.caller_auth.core import CredentialVerifier
registry = CredentialRegistry(backend_generation="g", profile_id="p", clock_ns=lambda: 1)
registry.install(CredentialVerifier.from_secret(secret, caller_id="c", backend_generation="g",
                 not_before_ns=0, expires_at_ns=2), profile_id="p")
result = registry.authenticate(base64.urlsafe_b64encode(secret).decode("ascii").rstrip("="))
assert result.authenticated is True
registry.rotate(CredentialVerifier.from_secret(replacement, caller_id="c", backend_generation="g",
                not_before_ns=0, expires_at_ns=2), profile_id="p", expected_epoch=1)
result = registry.check_context(result.context)
assert result.authenticated is False
result = registry.authenticate(base64.urlsafe_b64encode(replacement).decode("ascii").rstrip("="))
assert result.authenticated is True
registry.revoke()
result = registry.check_context(result.context)
assert result.authenticated is False
registry.close()
assert all(name.startswith("jarvis_agent.caller_auth") for name in sys.modules if name.startswith("jarvis_agent."))
assert len(threading.enumerate()) == 1
''', encoding="utf-8")
    env = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR", "PATH") if name in os.environ}
    env["PYTHONPATH"] = str(Path(module.__file__).resolve().parents[2])
    result = subprocess.run([sys.executable, "-B", str(script)], env=env, cwd=tmp_path,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
