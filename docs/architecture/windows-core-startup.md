# YJW-00B: native Windows Text/Core startup

## Scope and provenance

PR #6 / YJW-00A was externally accepted and squash-merged as
`495a6c63dde1b9bdc2fd3c657fdd1e1d5cd0574d`. All six checks in
[main CI 37655709548](https://github.com/YoungJibbit95/YJarvis/actions/runs/37655709548)
passed before the main HEAD was read again and `yjv2/w00b-windows-core-startup`
created. This PR changes startup only; the Python core and renderer are unchanged.

## Process boundary

`npm run dev` uses `scripts/dev.mjs` and the shared `scripts/startup.cjs` helper.
Node spawns executable/argv pairs with explicit environments and no shell.
The same Python discovery and ownership helper serves standalone Electron.
No dependency was added. Legacy macOS scripts remain available, but Bash is no
longer required by the supported development entry points.

The launcher probes Ollama's HTTP `/api/tags`, reuses an external server, or starts
`ollama serve` with the configured host. It starts the agent and waits for `/health`
(after SQLite initialization), then Vite and visible Electron. Only handles created
by the owner can be terminated: Windows uses `taskkill /PID /T /F`, POSIX uses a
separate owned process group. External backend mode creates no owned backend.
Cancellation prevents late Python fallback spawns; startup failure cleans up already
owned children. Backend paths with spaces and shell metacharacters remain data.

`dev:desktop` owns its backend/Vite/Electron but leaves Ollama external; direct
Electron launch still manages its own backend unless explicitly external.
Electron quit waits for its own backend cleanup. macOS activate/window-close
semantics remain: closing the last macOS window does not quit the application.
Backend cwd is consistently the repository root, including for relative overrides.

## Verification

Node startup tests cover both platform candidate lists, explicit interpreter
priority, argv/environment/path delimiters, spawn errors/fallback, missing Python,
external Ollama reuse, local Ollama spawn, cancellation, readiness failures and
literal shell metacharacters. A mocked Electron lifecycle test checks macOS
activation and repeated quit events while cleanup is pending. Real native backend tests cover health, SQLite's
baseline migration ledger, session persistence and owned shutdown with and without
Uvicorn reload. An external owner leaves the real backend alive. Both Python CI
jobs run these tests with Node 22, without npm dependencies, models or GUI.

Windows 11 Pro x64 10.0.26100 was manually tested on 2026-10-07 with Python 3.11.1,
Node 22.23.3, Electron 33.4.11, portable Ollama 0.40.0 and `qwen2.5:3b-instruct`:

- Native PowerShell `npm ci` and `npm run dev` succeeded with the project venv.
- Agent health returned `ok`; SQLite recorded baseline migration 1 and sessions.
- A visible Electron window loaded the actual UI and established its WebSocket.
- A text question entered in Electron reached local Ollama `/api/chat` (HTTP 200).
  The answer appeared in Electron with DONE and was persisted in SQLite.
- Normal window close ended the launcher with exit 0; ports 5173/8787/11434 and
  owned Electron/Ollama/model-runner processes were gone afterward.
- A separate forced Electron-exit check also cleaned up the owned stack.

The smoke used an isolated runtime/model directory under ignored `.git` state;
existing user databases, profiles and system-wide services were not replaced.
Exact automated results and final CI links are in the PR handoff.

## Limits, risks and rollback

The first cold model response took about 96 seconds and triggered the existing UI
watchdog message before the answer arrived. This is a functional smoke, not a
performance acceptance result. The existing macOS voice-list endpoint returns a
Windows error; text chat still completes with voice replies off. Audio/native tool
porting and UI/performance changes were deliberately not added.

macOS/Apple Silicon interactive runtime: **NOT RUN**. Audio/STT/TTS, OS tools,
Windows file safety and packaging: **NOT RUN / out of scope**. Existing npm audit
findings, unlocked transitive Python dependencies and absent server-enforced main
protection remain. Forced Windows cleanup is process-tree termination, not a
graceful Python shutdown; abrupt OS/process crashes remain outside this small
development helper's lifecycle guarantee.

Rollback is a revert of this PR, restoring the previous start commands. No schema
or personal runtime data requires rollback. Stop after handoff; no merge, YJW-01,
YJ2-04, audio or other next-step work before external review and explicit approval.
