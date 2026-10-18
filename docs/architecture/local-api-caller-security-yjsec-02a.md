# YJSEC-02A: Local API caller security foundation

Status: **inert foundation, D13 remains OPEN**. No productive authentication,
credential issuance, transport, provisioning, middleware, IPC handler or renderer
change is enabled. YJNX/G0-B remains independent; no Nexus integration is activated.

Baseline main: `bd78c84003b310b72eced2092873a060250c9185`, including accepted
YJSEC-01 (#44) and inert YJNX-01A (#45). Compared with the original V2 baseline
`dea0e9e6a266584e9c8efaf53dd82138aecbd662`, this already contains accepted
domain/persistence/orchestration/tool foundations, Windows providers/startup,
setup/packaging, UI/voice and communication changes. Their runtime behavior is
preserved. The user's explicit YJSEC-02A authorization supersedes historical
current-step markers; all architecture/review/stop gates remain in force.

## Current surface and inventory gate

[The complete inventory](../security/local-api-route-inventory.json) lists every
registered HTTP and WebSocket route, handler, current guard, protection need and
reason: 27 registrations, 30 HTTP method entries and one WebSocket CONNECT entry.
CONNECT denotes the WebSocket surface in the inventory, not a new HTTP method.
Four framework documentation/schema registrations include both GET and HEAD.

`tests/test_local_api_inventory.py` runs the actual application in a disposable
`python -I -B` process with an allowlisted environment and explicit synthetic
configuration. It compares exact transport/method/path/handler multiplicities
before startup, inside the real FastAPI lifespan context after startup, and after
controlled shutdown. This executes the existing database migrations/default seeding,
profile creation and setup startup/shutdown against temporary files, without
starting an HTTP/WS server. New, deleted, duplicated or changed registrations and
unknown/mounted applications fail the gate, including late startup/lifespan routes.
These are route-coverage tests, **not evidence that routes enforce authentication**.
The worker confirms database initialization, temporary profile creation, completed
shutdown, no remaining tasks/threads, minimal health contents, existing CORS and
absence of productive auth imports. Guarded application execution cannot create
sockets, resolve DNS, start child processes, open a database outside scratch, read
personal runtime/config files, or write outside scratch. Reads are limited to
scratch and source/toolchain roots; isolated Python disables user-site imports and
bytecode writes. Seven audit-only negative controls verify these restrictions
without performing the forbidden operation. The event loop is created before the
guards; application lifespan never needs new sockets. These Python audit guards
are fixture controls for trusted source, not an OS sandbox for hostile native code.

Synthetic regressions cover both startup handlers and custom lifespan contexts,
late HTTP/WebSocket registrations, duplicates and mounts. They verify cleanup
when the inventory comparison fails. They supplement, rather than replace, the
actual application's post-startup comparison.

## Inventory version 2: field definitions and planned ownership

The JSON is declarative test/review data only. Strict, closed Pydantic models in
the inventory test validate types and reject unknown fields; an independent exact
route/method policy matrix rejects incompatible combinations and unreviewed routes.
Neither these test models nor the policy data are imported by production code.

| Field | Type and meaning |
| --- | --- |
| `inventoryVersion` | Integer `2`; inventory metadata revision, unrelated to Nexus wire/schema versions. |
| `baselineMain` | Exact inspected baseline Git SHA. |
| `enforcement` | `planned-only-no-productive-authentication`; describes the real unchanged product state. |
| `routes` | Array of the 27 explicit registration records below. |
| `syntheticSurfaces` | Separate descriptions of `corsPreflight`, `slashRedirects`, `unmatchedRequests`; no executable exemptions. |
| `transport` | `http` or `websocket`. |
| `methods` | Nonempty, sorted, unique array of `GET`, `HEAD`, `POST`, `PUT`, `DELETE`, `CONNECT`, restricted to each reviewed route. |
| `path` / `handler` | Nonempty exact registered path and module/function identity; compared against actual registry multiplicities. |
| `protection` | `caller_required` or, only for GET `/health`, `bootstrap_liveness_only`. |
| `currentGuard` | Actual current caller-related guard: `none` or install POST/DELETE `origin_only`; neither is caller authentication. |
| `reason` | Nonempty explanation of protection need and actual data/side effects. |
| `policyStage` | Always `future_yjsec_02b`: caller and ownership requirements are not enforced or persisted by 02A. |
| `caller.allowedType` | `public_liveness` only for health; otherwise `authenticated_desktop_main`. Other client roles require explicit future review. |
| `caller.identitySource` | `none` for health; otherwise `future_trusted_backend_caller_and_profile_binding`, obtained from trusted authentication/provisioning, never Origin, URL, request ownership claims or session-ID knowledge. |
| `ownership.kind` | `none`, `global_metadata`, `profile`, `new_session`, `session`, `owned_session_collection`, `approval_session`. |
| `ownership.resourceIdentitySource` | `none`, `trusted_backend_profile`, `server_generated_session_id`, `path.session_id`, `body.session_id`, `database.approvals.session_id`, `path.approval_id_resolved_server_side`. Selectors identify resources, never prove ownership. |
| `ownership.ownerIdentitySource` | `not_applicable_liveness`, `not_applicable_global_metadata`, `future_backend_profile_caller_binding`, `future_session_owner_record`, or `database.approvals.session_id_and_future_session_owner_record`. |
| `ownership.requiredCheck` | One of the seven exact checks in the matrix below, matched to the route/selector/owner-source combination. |
| `ownership.reason` | Nonempty per-registration explanation, including explicit reasons for non-session/global/profile scope. |

All authenticated callers must be bound to the backend's trusted local profile.
An externally managed backend still requires a securely provisioned desktop Main
identity; external management is not an additional anonymous/admin caller role.
The future session-owner record must authoritatively bind a session to the verified
caller identity and backend profile, not to a bearer token, generation or supplied
owner field. Its schema, persistence, migration and restart/rotation identity policy
are **unimplemented YJSEC-02B work**. The current sessions schema does not store this
binding. `approvals.session_id` already exists, but does not itself authorize a caller.

| Ownership / routes | Required check and authoritative source |
| --- | --- |
| `none`: GET `/health` | `fixed_liveness_without_authority`: no owner/session/profile state. |
| `global_metadata`: docs/schema GET/HEAD and GET `/v1/setup/models` | `authenticate_profile_caller_without_session_owner`: static schema/catalog has no session owner; a verified profile-bound Main caller is still mandatory. |
| `profile`: settings, audio, Smart Home, setup inspection and installation | `match_caller_to_backend_profile`: use trusted backend-profile/caller binding; these endpoints are explicitly not session-bound. Host effects do not grant OS administration rights. |
| `new_session`: POST `/v1/sessions` | `persist_authenticated_caller_and_profile_before_publish`: attach the generated ID to the verified caller/profile before returning or publishing it. |
| `session`: messages and WebSocket `path.session_id`, chat `body.session_id` | `resolve_session_and_match_caller_and_profile`: resolve the selected session's future persisted owner record and compare verified caller/profile before data, run creation or WS accept/EventBus registration. |
| `owned_session_collection`: GET `/v1/approvals/pending` | `filter_approvals_to_owned_sessions_before_return`: resolve each stored `approvals.session_id`, check its session owner, and return only authorized sessions' approvals. |
| `approval_session`: POST `/v1/approvals/{approval_id}` | `resolve_approval_session_owner_before_existing_claim`: resolve the authoritative approval record to its stored session, check that session's owner, then retain the existing separate approval/policy/atomic-claim gates. A supplied approval ID is not permission. |

No current endpoint, persistence or approval-claim behavior is changed. Caller
authentication, resource ownership and tool/approval authorization remain distinct
gates. These fields neither implement ownership nor claim that D13 is complete.

Current caller authentication: **none**. Setup install POST/DELETE have only an
Origin allowlist. Native local clients can supply that header. Loopback, matching
CORS/Origin, a successful health check, session ID and approval ID are not identity.
Read-only routes can expose private data, probe the host or trigger external I/O;
they require caller authentication too. First-run setup is not a blanket exception.

Planned narrow bootstrap exceptions for 02B:

- GET `/health`: only the fixed `{"status":"ok"}` liveness response, without
  configuration, identifiers, paths, credentials or authority. It proves no backend
  identity. HEAD `/health` is not currently registered and is not implicitly public.
- A CORS preflight may negotiate an exact approved origin/method/header set only.
  It must never dispatch a handler, create a session, provision credentials or grant
  identity. Ordinary OPTIONS is not an exception. This middleware surface is recorded
  separately because it does not appear in `app.routes`.

Docs/OpenAPI must be authenticated or disabled in 02B. Slash redirects, errors,
unknown methods and future routes cannot become accidental exemptions. Protection
must precede request-body processing, file uploads, dependency/handler effects and
WebSocket accept/EventBus registration. Inventory policy is documentation/test data,
not an executable path matcher or current middleware allowlist.

## Inert verifier contract

`jarvis_agent.caller_auth.core` is OS-neutral, stdlib-only and imports no product
service. The application never imports it. It generates no credentials, reads no
environment, opens no files/sockets/database and performs no logging or process work.
There is no new dependency, feature flag, router or settings field.

`CredentialVerifier.from_secret` derives a SHA-256 verifier from **already securely
provisioned, CSPRNG-generated 32-byte material**. Length cannot prove entropy; this
is not a password API. Only the digest is retained, omitted from repr. Presented
credentials are exactly the canonical unpadded base64url encoding of those 32 bytes.
Whitespace, padding, prefixes, duplicate/combined values, noncanonical pad bits,
Unicode, oversized and non-string inputs are rejected; no normalization/fallback.
The core consumes the opaque value, not an Authorization header or URL.

Fixed-size digests are compared with `hmac.compare_digest`. After matching the
secret, the backend generation, revocation and half-open lifetime are checked.
`not_before_ns <= now_ns < expires_at_ns` uses the **same backend's monotonic clock**,
not Unix timestamps, client time or a clock shared between processes. Generation,
clock and immutable verifier snapshots are trusted inputs supplied by a future
lifecycle owner. Invalid context/configuration cannot authorize a caller.

Outcomes: `authenticated`, `unconfigured`, `invalid_context`, `missing_credential`,
`malformed_credential`, `invalid_credential`, `wrong_backend_generation`, `revoked`,
`not_yet_valid`, `expired`. Only `authenticated` returns a caller ID. Consumers must
check `.authenticated` explicitly; implicit truthiness raises. Wrong secrets reveal
no revocation/lifetime state. These diagnostic outcomes are internal; 02B must map
denials to bounded, generic HTTP/WS responses without echoing credentials.

The verifier is stateless. A `revoked=True` snapshot is rejected; this does **not**
implement a live revocation registry, concurrent rotation, expiry of established
sockets or restart recovery. Keeping an old snapshot would defeat live revocation.
02B must fetch current state per operation and invalidate active connections.
Caller authentication never authorizes a tool, approval, LLM policy or Nexus action.

## Credential exchange boundary for separately authorized YJSEC-02B

Trusted side: Electron Main and the explicitly owned Python backend process.
Renderer and page-controlled IPC payloads are lower-trust. Preload may expose narrow
typed operations/events, never a token getter, raw IPC object or arbitrary URL/header
proxy. Main validates sender webContents/main-frame identity and exact allowed
renderer location, validates payloads, owns HTTP/WS connections and attaches
credentials. Events return through bounded subscriptions. Existing `api.ts` direct
fetch/WebSocket calls therefore require coordinated migration; 02A does not alter them.
Electron's IPC guidance requires validating IPC senders; URL checks alone do not
authenticate a local network caller. [Electron security](https://www.electronjs.org/docs/latest/tutorial/security)

02B must define and test an authenticated, confidential bootstrap channel **before**
any credential is sent. Candidate: private inherited anonymous pipe/handle between
the owner and its exact child, carrying per-start material and backend identity,
followed by a pinned, confidential loopback transport for HTTP/WS. An unauthenticated
health response or occupied port cannot authenticate the peer: port replacement
must not trick Main into sending its token to a different process. Exact handle/FD
inheritance, peer binding, server identity and certificate lifecycle remain 02B
design/review work; no mechanism is implemented or claimed here. No shared file,
public bootstrap endpoint or bearer secret in an environment variable/argv is proposed.

| Lifecycle | Required 02B boundary and acceptance evidence |
| --- | --- |
| Development | `scripts/dev.mjs` currently owns Python, starts Vite and marks Electron's backend external. Consolidate trusted ownership or explicitly authenticate the CLI-to-Main handoff. No token in Vite variables, dev-server assets, hot reload, renderer or inherited ambient environment. |
| Installed Windows | Main owns the frozen EXE via `packaged.cjs`; use private child-only handles, close unused inherited handles, bind identity/endpoint and keep credentials in process memory. NSIS installation/resources contain no credential. Test install, launch, restart, uninstall and stale-port replacement. |
| Installed macOS | Same logical boundary for the bundled backend and Main; use correctly scoped inherited FDs/private IPC and actual native lifecycle tests. No credential embedded in ASAR, DMG, app bundle or plist. Linux CI cannot prove macOS handle/permission behavior. |
| Restart/reload/crash | Fresh generation and credential, fresh verifier and monotonic lifetime; invalidate old records and sockets. Bound TTL, close/rotate on shutdown, avoid stale caches. Reconnect only after authenticated re-bootstrap; never automatically replay an uncertain mutation. Reload workers require explicit ownership/secret-transfer design. |
| Externally managed backend | Current `JARVIS_BACKEND_MANAGED=external` skips process ownership. Require explicit trusted provisioning and authenticated peer binding under the external manager; do not adopt a backend merely because health succeeds. Unsupported secure provisioning must fail closed after activation, without anonymous fallback or terminating the external process. Remote hosts need a separately approved transport policy. |

Neither browser WebSocket URLs nor subprotocols are credential carriers. Browser
WebSocket construction exposes URL/subprotocol parameters, not an arbitrary header
API; a coordinated Main-owned transport avoids putting a secret in either.
[WebSocket constructor](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/WebSocket)

02B acceptance scope: complete HTTP/WS enforcement and authoritative caller/profile/
session/approval ownership against this inventory, including new-session binding
and filtering pending approvals; strict
unambiguous header parsing; Main/preload broker and renderer migration; secure
bootstrap/peer binding in every supported lifecycle; current-state revocation,
generation/TTL rotation and socket invalidation; narrowly bounded health/preflight
exceptions; redaction across logs, crash/errors and build/test artifacts; installer,
startup and actual Windows/macOS smoke tests. No token in URLs, Git, settings/DB,
renderer bundles, debugging output or persisted test fixtures. Keep D14-D16, Nexus,
ToolRuntime, planner, voice and approval-claim behavior outside the package.

## Evidence, risks and rollback

Run `python -m pytest -q tests/test_local_caller_auth.py tests/test_local_api_inventory.py`,
then the complete Python/Ruff, Startup, Desktop and CI baseline in CONTRIBUTING.
Tests create only ephemeral dummy material in memory; no credential fixture is
saved. The route inventory is exercised without live endpoints or downloads.
Isolation tests prohibit productive imports and audit cold import for resource work.
P2-1 regressions reject missing/unknown metadata, untrusted caller/owner sources,
invalid stage/type values and validly typed but incompatible ownership combinations.
P2-2 regressions cover startup and lifespan registry drift plus shutdown/resource
evidence from the actual app. All original 97 cases remain; no verifier change.
Digest comparison follows [Python hmac](https://docs.python.org/3.11/library/hmac.html#hmac.compare_digest);
future issuance must use explicit strong randomness, e.g.
[Python secrets](https://docs.python.org/3.11/library/secrets.html).

The existing API remains unauthenticated after this PR. A valid decision proves only
possession against the supplied trusted snapshot. It does not prove safe provisioning,
server identity, live revocation, permission to access a particular session or
durable/crash-safe state. Bearer possession can be replayed within its lifetime;
compromised same-user processes, memory/debugger access and a compromised trusted
Main/backend are not solved by this primitive. No native macOS execution is claimed.

Rollback: revert this isolated foundation PR. No runtime call path, database,
configuration, user data or existing credential has to be migrated or deleted.
External review must examine the actual diff and these limits. D13 completion and
YJSEC-02B require separate explicit approval. No self-merge or following implementation.
