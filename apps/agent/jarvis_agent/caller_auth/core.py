"""Pure credential verification, deliberately disconnected from the application.

Only trusted provisioning may supply a verifier, generation and monotonic time.
An authenticated caller is not an authorized tool action or approval decision.
"""

import base64
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import hmac
import re


_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}", re.ASCII)


class AuthStatus(Enum):
    AUTHENTICATED = "authenticated"
    UNCONFIGURED = "unconfigured"
    INVALID_CONTEXT = "invalid_context"
    MISSING = "missing_credential"
    MALFORMED = "malformed_credential"
    INVALID = "invalid_credential"
    WRONG_GENERATION = "wrong_backend_generation"
    REVOKED = "revoked"
    NOT_YET_VALID = "not_yet_valid"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class AuthDecision:
    status: AuthStatus
    caller_id: str | None = None

    @property
    def authenticated(self) -> bool:
        return self.status is AuthStatus.AUTHENTICATED

    def __bool__(self) -> bool:
        raise TypeError("Check decision.authenticated explicitly")


def _identifier(value: object) -> bool:
    return type(value) is str and _IDENTIFIER.fullmatch(value) is not None


def _tick(value: object) -> bool:
    return type(value) is int and value >= 0


@dataclass(frozen=True, slots=True)
class CredentialVerifier:
    """Trusted, immutable snapshot, never deserialize this from a caller request.

    Tick values belong to one backend's monotonic clock, not Unix timestamps.
    The digest is for a CSPRNG-generated 32-byte secret, never a human password.
    No plaintext, issuer, clock, registry, revocation store or I/O is retained.
    """

    caller_id: str
    backend_generation: str
    digest: bytes = field(repr=False)
    not_before_ns: int
    expires_at_ns: int
    revoked: bool = False

    def __post_init__(self) -> None:
        if not (_identifier(self.caller_id) and _identifier(self.backend_generation)):
            raise ValueError("Invalid verifier identity")
        if type(self.digest) is not bytes or len(self.digest) != 32:
            raise ValueError("Invalid verifier digest")
        if not (_tick(self.not_before_ns) and _tick(self.expires_at_ns)
                and self.expires_at_ns > self.not_before_ns):
            raise ValueError("Invalid verifier lifetime")
        if type(self.revoked) is not bool:
            raise ValueError("Invalid verifier revocation state")

    @classmethod
    def from_secret(
        cls, secret: bytes, *, caller_id: str, backend_generation: str,
        not_before_ns: int, expires_at_ns: int, revoked: bool = False,
    ) -> "CredentialVerifier":
        """Derive a verifier from already securely provisioned random material."""
        if type(secret) is not bytes or len(secret) != 32:
            raise ValueError("Expected 32 bytes of provisioned random material")
        return cls(caller_id, backend_generation, hashlib.sha256(secret).digest(),
                   not_before_ns, expires_at_ns, revoked)


def authenticate(
    presented: object, *, verifier: CredentialVerifier | None,
    backend_generation: str, now_ns: int,
) -> AuthDecision:
    """Verify one opaque token; every outcome except AUTHENTICATED denies.

    Token spelling: canonical, unpadded base64url of exactly 32 random bytes.
    This is not an HTTP header parser or a WebSocket handshake. Network address,
    Origin, CORS, session IDs and bootstrap routes cannot supply credentials.
    Diagnostic states stay internal; future adapters must not echo credentials.
    """
    if not _identifier(backend_generation) or not _tick(now_ns):
        return AuthDecision(AuthStatus.INVALID_CONTEXT)
    if verifier is None:
        return AuthDecision(AuthStatus.UNCONFIGURED)
    if type(verifier) is not CredentialVerifier:
        return AuthDecision(AuthStatus.INVALID_CONTEXT)
    if presented is None:
        return AuthDecision(AuthStatus.MISSING)
    if type(presented) is not str or _TOKEN.fullmatch(presented) is None:
        return AuthDecision(AuthStatus.MALFORMED)
    secret = base64.urlsafe_b64decode(presented + "=")
    if base64.urlsafe_b64encode(secret).decode("ascii").rstrip("=") != presented:
        return AuthDecision(AuthStatus.MALFORMED)
    # Both operands are fixed 32-byte digests; no plaintext equality comparison.
    if not hmac.compare_digest(hashlib.sha256(secret).digest(), verifier.digest):
        return AuthDecision(AuthStatus.INVALID)
    # Wrong secrets never reveal the trusted record's lifetime/revocation state.
    if verifier.backend_generation != backend_generation:
        return AuthDecision(AuthStatus.WRONG_GENERATION)
    if verifier.revoked:
        return AuthDecision(AuthStatus.REVOKED)
    if now_ns < verifier.not_before_ns:
        return AuthDecision(AuthStatus.NOT_YET_VALID)
    if now_ns >= verifier.expires_at_ns:
        return AuthDecision(AuthStatus.EXPIRED)
    return AuthDecision(AuthStatus.AUTHENTICATED, verifier.caller_id)
