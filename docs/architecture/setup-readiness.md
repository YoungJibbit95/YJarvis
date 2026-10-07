# YJUX-01A — Read-only setup readiness and first-run gate

## Authorization and baseline

The user's accepted external review of YJUX-00B explicitly authorizes this
Product Experience step after PR #14's squash merge and six green main checks.
PR #14 merged as `65a3d974adb4f8e2e9ba72fe5d47a5b9b44b95ab`;
[all six post-merge jobs passed](https://github.com/YoungJibbit95/YJarvis/actions/runs/37697320292)
before `codex/yjux-01a-setup-readiness` was created. This later instruction
supersedes the Core track's UI exclusions for this step only.

Core PR #13 was initially open with no overlap. During implementation it merged
as `a79cc256ae0d4bc2df4f0a631812f5a1f7d83b97`. This branch fast-forwarded to that
main before its implementation commit. The ten incoming files were the expected
Core guidance, input contracts/catalog, architecture notes and tests/fixtures;
none touched `main.py`, API transport or desktop code. The final PR records the
fresh publication-time overlap check. The separate Core checkout is never edited.

## Boundaries and inspection

`setup_readiness.py` owns the read-only checks and the small response models.
`setup_api.py` exposes `GET /v1/setup/status`, injected with the existing settings
reader and default Whisper path. `main.py` only registers that router. There are
no changes to backend/process startup, TurnEngine, routing, planning, ToolSpec, policy, providers,
memory, persistence/schema or the existing audio implementation.

The endpoint reads current persisted settings on each request, with no caching.
It makes at most one GET to the configured Ollama base URL plus `/api/tags`, preserving
the existing LLM client's URL composition. Redirects and environment proxies are
disabled. HTTP timeout is three seconds and the complete GET is bounded to four
seconds. Non-HTTP(S)/malformed base URLs are errors. Connection/timeouts mean
unreachable; HTTP errors, malformed JSON and invalid inventories mean error,
never ready or an invented missing-model verdict.

Model names match exactly with only Ollama's documented omitted `:latest` tag
normalization. No existing Python name normalizer was found. There is no fuzzy
match, model recommendation, inference request or model load. Sources:
[GET model inventory](https://docs.ollama.com/api/tags) and
[model-name conventions](https://github.com/ollama/ollama/blob/main/docs/api.md#model-names).
Presence does not prove chat capability, sufficient memory or successful inference.

STT uses the existing configured-path/default-Whisper-path choice. Only stat is
used: a non-empty regular file is present; missing/empty/directory paths are
missing; unreadable paths are unknown. No format/content validation, executable,
microphone, audio device or transcription test is implied.

For Piper, a missing configured model file is reported. An existing Piper file,
system voice or other engine remains **unknown** because 01A cannot reliably
prove voice readiness without broader audio work. No `say` voice enumeration,
audio import/probe, synthesis, playback or subprocess occurs in the setup check.

## Explicit state matrix

Component states are `available`, `missing`, `unreachable`, `unknown`, `error`,
with machine-readable reason codes. UI text is derived from these fields;
human-readable runtime error strings never determine state.

| Required chat prerequisite | Optional STT/TTS | Overall state | New chat input |
| --- | --- | --- | --- |
| Inspection pending | Any | `checking` (frontend) | Disabled |
| Model missing/unconfigured or endpoint unreachable | Any | `needs_setup` | Disabled |
| Inspection unreliable/invalid | Any | `error` | Disabled |
| Model present | At least one missing, unknown, unreachable or error | `degraded` | Enabled |
| Model present | Both confirmed available | `ready` | Enabled |

Agent connectivity reuses the existing desktop `/health` wait (45 seconds),
moved before App mounts. It is not another backend health subsystem. Frontend
requests can be aborted and the whole attempt has a 50-second deadline. A failed
agent connection, failed setup request or invalid/inconsistent DTO is `error`.
Aborted/older checks cannot replace the current result.

**01A's real inspector intentionally emits degraded for usable text chat:** TTS
is never claimed available here. `ready` is the explicit all-confirmed contract
and renderer branch, verified with a controlled DTO fixture, not evidence that
this machine has working voice. This conservative limit must not be bypassed
merely to show a green state. No future audio/provider implementation is included.

## First run and app access

`SetupGate` owns only inspection, retry and a non-persisted entry choice. Before
the first result it shows checking; needs_setup/error show the first-run screen.
When the backend is reachable, “Später · App ansehen” opens the existing AppShell
even if setup is incomplete. Otherwise retry remains available. No dismissed or
completed flag is stored: every launch inspects actual prerequisites again.

Ready/degraded enter the normal shell. Its persistent status disclosure displays
all components and retry. Once App is mounted it remains mounted across checks,
so session, settings drafts and approvals are not reset. Saving settings retains
the existing explicit PUT and then triggers a read-only recheck. No setup action
saves settings or executes an approval. The four navigation destinations remain.

Without confirmed chat prerequisites, composer, Quick Actions, global prompt
commands and voice-start entry are disabled and the submission boundary is
guarded. A recheck temporarily blocks new submissions, clears queued voice
input and stops capture using existing cleanup; late permission/segment results
cannot submit while blocked. Existing in-flight agent runs are not cancelled.
This is a desktop product gate, **not** new backend execution/approval policy;
existing API clients and deterministic Core paths retain their contracts.
Voice handling for ready/degraded is otherwise unchanged, including known errors.

## Side-effect audit and verification

- Setup endpoint: existing settings SELECTs, one HTTP GET, path stat only.
- No downloads, installations, process spawning, generated model files, settings
  writes, provider activation, tool calls or Core lifecycle changes.
- Existing App/session initialization occurs only after entry; its normal effects
  are distinct from a setup status check. The existing voice-list error can still
  appear after entry and is not hidden/repaired here.
- Tests exercise the component-state matrix, exact model/tag matching, missing
  and invalid inventories, connection failures, invalid endpoints and file states.
- Side-effect tests block process/file mutation APIs and compare settings/paths.
  API integration uses real temporary SQLite and compares its entire logical dump
  before/after repeated GETs; POST to the setup endpoint is unsupported.
- Renderer verification uses an isolated real agent/temporary database and a
  controlled local Ollama inventory. Ready, delayed and malformed DTOs use an
  external preview fixture, never a production flag or endpoint. Tests do not prove
  model inference, STT or TTS. PR evidence lists exact commands and actual results.

No new dependencies or frontend framework. Electron smoke, macOS/Apple Silicon,
native audio, high-DPI hardware and packaged-app verification are NOT RUN when
unavailable. File presence and a current inventory are snapshots, not guarantees
of ongoing availability. Manual retry and explicit settings save refresh them.

## Rollback and stop gate

Revert this PR's implementation commit (or eventual squash commit). Existing data,
settings and API contracts need no migration or cleanup; retain runtime data.
Model catalogs, downloads/installers, hardware recommendations, voice repairs and
YJUX-01B remain out of scope. Stop after a green PR and external-review handoff;
do not merge this implementation PR or start further work without authorization.
