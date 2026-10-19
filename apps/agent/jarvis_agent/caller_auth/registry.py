"""Inert, current credential state; no provisioning or application integration.

Only a trusted owner may install/rotate records. The injected monotonic clock
must be bounded, non-reentrant and share the verifier's backend timebase.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum
from threading import Lock

from .core import AuthStatus, CredentialVerifier, _identifier, _tick, authenticate


class RegistryState(Enum):
    EMPTY = "empty"
    CONFIGURED = "configured"
    REVOKED = "revoked"
    EXPIRED = "expired"
    CLOSED = "closed"
    FAULTED = "faulted"


class RegistryDenial(Enum):
    CLOSED = "registry_closed"
    STALE_CONTEXT = "stale_context"


@dataclass(frozen=True, slots=True)
class CallerContext:
    """Historical identity, not standalone authority; recheck with its registry."""

    caller_id: str
    profile_id: str
    backend_generation: str
    epoch: int
    _registry_tag: object = field(repr=False, compare=False)

    def __bool__(self) -> bool:
        raise TypeError("Recheck context with its registry explicitly")


@dataclass(frozen=True, slots=True)
class RegistryDecision:
    status: AuthStatus | RegistryDenial
    context: CallerContext | None = None

    @property
    def authenticated(self) -> bool:
        return self.status is AuthStatus.AUTHENTICATED and self.context is not None

    def __bool__(self) -> bool:
        raise TypeError("Check decision.authenticated explicitly")


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    """Diagnostic state only. CONFIGURED does not assert current authentication."""

    caller_id: str | None
    profile_id: str
    backend_generation: str
    epoch: int
    state: RegistryState


class CredentialRegistry:
    """One immutable generation/profile and one caller, bound on first install.

    Each operation linearizes under one lock, after reading the clock and before
    releasing the lock. No decision reserves future execution. Retained snapshots
    cannot be submitted as verifiers; contexts require check_context per admission.
    Retired digests remain in memory until disposal to prevent record resurrection.
    """

    __slots__ = ("_generation", "_profile", "_clock", "_lock", "_tag", "_caller",
                 "_verifier", "_seen", "_epoch", "_state", "_last_tick")

    def __init__(self, *, backend_generation: str, profile_id: str,
                 clock_ns: Callable[[], int]) -> None:
        if not (_identifier(backend_generation) and _identifier(profile_id)
                and callable(clock_ns)):
            raise ValueError("Invalid registry configuration")
        self._generation = backend_generation
        self._profile = profile_id
        self._clock = clock_ns
        self._lock = Lock()
        self._tag = object()
        self._caller: str | None = None
        self._verifier: CredentialVerifier | None = None
        self._seen: set[bytes] = set()
        self._epoch = 0
        self._state = RegistryState.EMPTY
        self._last_tick: int | None = None

    def __copy__(self):
        raise TypeError("Registry state cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("Registry state cannot be copied")

    def __reduce_ex__(self, protocol):
        raise TypeError("Registry state cannot be serialized")

    def _now(self) -> int | None:
        # Caller holds the lock. Clock faults are terminal, including later
        # apparently valid readings: expired credentials must never reactivate.
        if self._state in (RegistryState.CLOSED, RegistryState.FAULTED):
            return None
        try:
            now = self._clock()
        except Exception:
            now = None
        if not _tick(now) or (self._last_tick is not None and now < self._last_tick):
            self._state = RegistryState.FAULTED
            self._verifier = None
            self._epoch += 1
            return None
        self._last_tick = now
        if (self._state is RegistryState.CONFIGURED and self._verifier is not None
                and now >= self._verifier.expires_at_ns):
            self._state = RegistryState.EXPIRED
        return now

    def _snapshot(self) -> RegistrySnapshot:
        return RegistrySnapshot(self._caller, self._profile, self._generation,
                                self._epoch, self._state)

    def snapshot(self) -> RegistrySnapshot:
        with self._lock:
            self._now()
            return self._snapshot()

    def _accept(self, verifier: CredentialVerifier, profile_id: str, now: int) -> None:
        if (type(verifier) is not CredentialVerifier or not _identifier(profile_id)
                or profile_id != self._profile):
            raise ValueError("Invalid registry binding")
        if (verifier.backend_generation != self._generation
                or (self._caller is not None and verifier.caller_id != self._caller)):
            raise ValueError("Invalid registry binding")
        if (verifier.revoked or verifier.expires_at_ns <= now
                or verifier.digest in self._seen):
            raise ValueError("Credential record cannot be installed")
        self._seen.add(verifier.digest)
        self._caller = verifier.caller_id
        self._verifier = verifier
        self._epoch += 1
        self._state = RegistryState.CONFIGURED

    def install(self, verifier: CredentialVerifier, *, profile_id: str) -> RegistrySnapshot:
        """Trusted initial registration only; duplicate install never replaces state."""
        with self._lock:
            now = self._now()
            if now is None or self._state is not RegistryState.EMPTY:
                raise ValueError("Registry cannot accept initial registration")
            self._accept(verifier, profile_id, now)
            return self._snapshot()

    def rotate(self, verifier: CredentialVerifier, *, profile_id: str,
               expected_epoch: int) -> RegistrySnapshot:
        """Atomic compare-and-swap; fresh material may replace revoked/expired state."""
        with self._lock:
            now = self._now()
            if (now is None or self._caller is None or not _tick(expected_epoch)
                    or expected_epoch != self._epoch):
                raise ValueError("Registry rotation rejected")
            self._accept(verifier, profile_id, now)
            return self._snapshot()

    def revoke(self) -> RegistrySnapshot:
        """Invalidate current credentials/contexts; repeated revocation is idempotent."""
        with self._lock:
            self._now()
            if self._state in (RegistryState.CONFIGURED, RegistryState.EXPIRED):
                assert self._verifier is not None
                self._verifier = replace(self._verifier, revoked=True)
                self._state = RegistryState.REVOKED
                self._epoch += 1
            return self._snapshot()

    def close(self) -> RegistrySnapshot:
        """Terminal denial; a generation change requires a separate empty registry."""
        with self._lock:
            if self._state is not RegistryState.CLOSED:
                self._state = RegistryState.CLOSED
                self._verifier = None
                self._epoch += 1
            return self._snapshot()

    def _denial(self) -> RegistryDecision | None:
        status = {
            RegistryState.EMPTY: AuthStatus.UNCONFIGURED,
            RegistryState.CLOSED: RegistryDenial.CLOSED,
            RegistryState.FAULTED: AuthStatus.INVALID_CONTEXT,
        }.get(self._state)
        return RegistryDecision(status) if status is not None else None

    def authenticate(self, presented: object) -> RegistryDecision:
        with self._lock:
            now = self._now()
            denial = self._denial()
            if denial is not None:
                return denial
            # All trusted states here retain their verifier, including revocation
            # and expiry, so wrong secrets retain the core's INVALID precedence.
            assert self._verifier is not None and now is not None
            decision = authenticate(presented, verifier=self._verifier,
                                    backend_generation=self._generation, now_ns=now)
            if not decision.authenticated:
                return RegistryDecision(decision.status)
            context = CallerContext(self._verifier.caller_id, self._profile,
                                    self._generation, self._epoch, self._tag)
            return RegistryDecision(AuthStatus.AUTHENTICATED, context)

    def check_context(self, context: object) -> RegistryDecision:
        """Check current identity/epoch/lifetime, without replaying an old decision."""
        with self._lock:
            now = self._now()
            denial = self._denial()
            if denial is not None:
                return denial
            if (type(context) is not CallerContext or context._registry_tag is not self._tag
                    or not _tick(context.epoch) or context.epoch != self._epoch
                    or not all(_identifier(value) for value in (
                        context.caller_id, context.profile_id, context.backend_generation))
                    or context.caller_id != self._caller or context.profile_id != self._profile
                    or context.backend_generation != self._generation):
                return RegistryDecision(RegistryDenial.STALE_CONTEXT)
            if self._state is RegistryState.REVOKED:
                return RegistryDecision(AuthStatus.REVOKED)
            if self._state is RegistryState.EXPIRED:
                return RegistryDecision(AuthStatus.EXPIRED)
            assert self._verifier is not None and now is not None
            if now < self._verifier.not_before_ns:
                return RegistryDecision(AuthStatus.NOT_YET_VALID)
            return RegistryDecision(AuthStatus.AUTHENTICATED, context)
