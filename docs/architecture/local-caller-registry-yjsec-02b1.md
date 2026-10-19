# YJSEC-02B / B1: inert current credential registry

Status: **B1 implemented, pending independent security review. D13 remains OPEN.**
No productive authentication is activated. No merge or B2–B8 implementation is
authorized. The existing local API remains unauthenticated.

## Scope and source

Base: `32fd26a695d0c690d9e6e82facbed093cb3b88f8`, the actual remote main inspected
before implementation. It includes accepted YJSEC-01, YJNX-01A and corrected
[YJSEC-02A](local-api-caller-security-yjsec-02a.md). The original V2 baseline
`dea0e9e6a266584e9c8efaf53dd82138aecbd662` predates the accepted domain,
persistence, orchestration, provider, Windows startup/packaging, setup, UI/voice,
communication and security foundations. None of those paths changes here.

The user's explicit B1 instruction supersedes historical current-step markers
and requests a Draft PR. The locally prepared `implementation/owned-tls.md` and
`implementation/core-worker-b1.md` (architecture collection
`03cf635be70813386ed6779282264dfeddace765d1f99be5f972777702498a36`) define the B1
boundary. Their B2–B8 descriptions remain proposals. No substantive B1 contract
conflict was found. This document records the concrete API left open by that plan.

Changes: one stdlib-only registry, its isolated tests, this note, and exactly the
authorized `registry.py -> core.py` import exception in the existing isolation
test. `core.py` remains byte-identical, blob
`11e52b02d9bd8621d81c67d6d9bf171e7cf94e5b`. Package initialization, routes,
inventory, startup, Electron, packaging, dependencies, approval claim and Nexus
contracts remain unchanged.

## Trusted interface

`CredentialRegistry(backend_generation=..., profile_id=..., clock_ns=...)` fixes
one generation and one security profile. The empty registry denies authentication.
The first trusted `install(verifier, profile_id=...)` binds its one canonical
caller, consistent with the proposed initial Desktop-Main operating profile.
Neither profile nor caller is accepted from an authentication request.

| Operation | Contract |
| --- | --- |
| `install` | Initial registration only. Exact `CredentialVerifier`, matching generation/profile, non-revoked, not expired, previously unused digest. Reject duplicate installation. |
| `rotate` | Same caller/profile/generation, fresh digest and exact integer `expected_epoch`. Compare-and-swap under the lock; stale owners cannot overwrite a newer transition. Explicit fresh rotation may replace revoked or expired state. |
| `authenticate` | Opaque credential only; invoke unchanged core on the current verifier. Success returns immutable `CallerContext` with trusted caller/profile/generation/epoch. |
| `check_context` | Recheck registry instance, all identity fields, current epoch, lifetime and lifecycle. A copied DTO or context from another registry is not authority. |
| `snapshot` | Immutable public diagnostic metadata; no credential, digest or verifier. `CONFIGURED` does not mean a credential was presented or is already valid. |
| `revoke` | Invalidate the current credential and all issued contexts atomically. Repetition is idempotent. Revoke on an empty registry leaves it empty. |
| `close` | Terminal denial, also when empty or faulted; discard current verifier. Generation change requires a separate empty registry with fresh provisioned material. |

No issuer, global registry, default clock, settings flag, persistent record,
network adapter or provisioning entry exists. Registry creation occurs only when
explicitly called. Internal locking starts no worker, task or timer.

## Lifecycle and ordering

Every public operation acquires the same lock. Clock observation, verification,
state changes and result construction occur while holding it. Its decision is
binding only at that operation's linearization point inside the lock; after lock
release it is historical evidence. A snapshot cannot be passed to authentication
as a verifier. A context must return to `check_context` for each new admission.

An authentication already ordered before revocation may succeed. Every new
registry check ordered after revocation denies that old identity/epoch. B1 does
not reserve an operation, interrupt work, retract bytes or close sockets. Future
transport adapters must enforce their own admission/send ordering and invalidation;
retaining `.authenticated=True` from an earlier decision is not a live permission.

Rotation increments the epoch once; revocation increments it on its first actual
transition; close and terminal clock fault each invalidate the epoch. Rejected
configuration/rotation does not replace the prior accepted binding. Invalid clock
input instead permanently faults the whole registry and discards its verifier.

The injected clock is a trusted, bounded, non-reentrant callable returning exact
nonnegative integer nanoseconds from the same backend's monotonic timebase used
by the verifier. No request-supplied `now` or wall-clock conversion is accepted.
The core's half-open validity interval is preserved. Backwards time, invalid types
and clock exceptions permanently deny, even if a later reading looks correct.
There is no background expiry timer: admission/snapshot checks observe expiration.

Every accepted digest is retained privately until registry disposal. Old verifier
objects, including records with edited expiration/revocation fields, cannot
reactivate that material through rotation. Copy/deepcopy/pickle of a registry is
rejected. Contexts carry an opaque instance marker omitted from repr, unrelated
to credential material; serializing public identity fields cannot recreate it.

Core denial values and constant-size secret comparison remain unchanged. Wrong
secrets continue to return `invalid_credential` before record lifecycle details.
Registry-only denials add `registry_closed` and `stale_context`; a clock fault
returns `invalid_context`. Denials contain no context. Decision/context implicit
truthiness raises. Internal diagnostics are not a future HTTP response contract.

## Evidence and limitations

Run the unchanged core/inventory cases plus `tests/test_local_caller_registry.py`.
Tests cover empty and malformed state, caller/profile/generation mismatch,
half-open validity, terminal clock failures, duplicate registration, old snapshots,
rotation/CAS, revocation/close, synthetic secrets, redaction and parallel access.
Barrier/event tests force a reader to hold the lock while rotation/revoke/close
attempts to run; multiple competing rotations have exactly one CAS winner.

Cold-import/lifecycle audit checks reject socket, subprocess, database, native
library and file-write work and thread startup. AST gates allow only stdlib and
the exact internal core edge; all other product auth imports remain prohibited.
The unchanged actual FastAPI lifespan inventory checks 27 registrations / 31
method entries and zero productive auth imports. These controls complement source
review; Python audit hooks are not a sandbox against hostile native code.

All new credentials are generated transiently by tests using `secrets.token_bytes`;
none are fixture literals, stored files, test IDs or logs. Registry snapshots,
decisions and normal repr/errors contain neither token nor digest. This does not
promise safe memory erasure, resistance to a debugger, hostile Python code with
object access, or arbitrary caller-supplied clock/provisioning implementations.
The digest tombstone set grows with trusted rotations for this in-memory lifetime.

Instance-local state cannot police a separate process or independently constructed
registry that is deliberately provisioned with reused secret material. The trusted
future lifecycle owner must close the old registry, choose a fresh generation and
fresh random material; old-generation verifiers cannot be installed into the new
one. This is not restart recovery or a durable global revocation store.

No test here proves HTTP/WS enforcement, peer identity, resource/session ownership,
approval authorization, provisioning, TLS, socket invalidation or native platform
qualification. Those remain B2–B8 work needing separate authorization. No macOS
native execution is claimed. Exact local/CI commands and results accompany the PR.

## Rollback and review gate

Revert the isolated B1 change: remove the registry, its tests and note, and restore
the exact original import gate. No database, credential, settings, user-data or
runtime migration is needed. Have independent reviewers examine locking,
linearization, epoch/lifetime semantics, secret handling and absence of productive
imports against the actual diff. Green CI is not approval. Stop before merge.
