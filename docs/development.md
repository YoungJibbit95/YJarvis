# Local development and baseline checks

## What this baseline covers

YJ2-00 added CI and review guardrails; YJ2-01 through YJ2-03 added inert domain
contracts, migration infrastructure and an orchestration extraction. YJW-00A
adds a native Windows automated baseline. Windows 11 x64 is the primary current
development target; macOS Apple Silicon remains first-class, with the existing
macOS runtime setup below. Automated checks run on Ubuntu 24.04 and the x64
`windows-2025` runner with Python **3.11.x** (`.python-version`) and Node.js **22.x**
(`.nvmrc`). YJW-00B adds shared native Windows/macOS Text/Core startup. Patch
versions are logged by CI; native tools/audio and packaging remain separate work.

The committed npm lockfile supplies the JavaScript dependency graph. Python
runtime dependencies are pinned directly in both `apps/agent/requirements.txt`
and `apps/agent/pyproject.toml`; they are intentionally unchanged by YJ2-00.
Transitive Python dependencies are not fully locked: CI records `pip freeze` and
runs `pip check` so the resolved environment can be inspected. Development-only
`pytest` and Ruff versions are pinned in `requirements-dev.txt`.
That file also pins `tzdata` on Windows for the DST contract test; production code
currently does not construct IANA `ZoneInfo` objects. Runtime manifests are unchanged.

## Native Windows automated checks (YJW-00A)

With Python 3.11 and Node 22 installed, run from the repository root in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps/agent/requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check apps/agent/jarvis_agent tests
npm run test:startup
node --version
npm --version
npm ci
npm run typecheck
node --check apps/desktop/electron/main.cjs
node --check apps/desktop/electron/preload.cjs
npm run build
```

Run each check and inspect its exit status; do not mask an earlier failure with a
later command. Direct interpreter paths avoid activation/execution-policy changes.
No WSL, Git Bash, model server or audio device is needed. Windows wheels supply
the libraries needed to import the existing audio dependencies during these tests.
CI skips downloading Electron's binary for static checks; normal installs do not.

These commands test the core, real backend startup/cleanup and static desktop code.
No models or GUI are needed for `test:startup`; it uses disposable SQLite databases.
Native tool/audio providers are still legacy runtime paths. See the
[Windows baseline note](architecture/windows-test-ci-baseline.md) for the three
test fixes, retained assertions and verification limits.

## Native Windows Text/Core setup (YJW-00B)

Upstream instructions checked on 2026-10-07:

1. Install the [official Python Install Manager](https://docs.python.org/3/using/windows.html),
   then `pymanager install 3.11`. An existing Python 3.11 installation also works;
   verify `py -3.11 --version` before creating the venv. The startup helper uses
   executable paths, not a combined `py -3.11` command string.
2. Install **Node 22 x64** from the [official download selector](https://nodejs.org/en/download)
   (select the project's 22.x line). Reopen PowerShell and check `node --version`
   and `npm --version`.
3. Install [Ollama for Windows](https://docs.ollama.com/windows) using its official
   installer, or extract its standalone Windows CLI archive and add that directory
   to the current shell's PATH. No Bash/WSL, curl or system-wide service is required.

From the repository root in native PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps/agent/requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
npm ci
```

If Ollama is not already running, run `npm run dev:ollama` in another PowerShell
terminal. Download the configured text model once (outside CI):

```powershell
ollama pull qwen2.5:3b-instruct
npm run dev
```

`npm run dev` reuses a responding Ollama server or starts `ollama serve`, waits for
HTTP readiness, starts the agent and migrations, then Vite and a visible Electron
window. `dev:desktop` starts agent/Vite/Electron without managing Ollama.
Electron launched directly retains its own backend management. Every entry point
respects `JARVIS_BACKEND_MANAGED=external`; it never stops that external backend.
Close Electron (Windows) or quit the app (macOS), or use Ctrl-C in the launch
terminal. Only owned children are stopped. Windows cleanup uses `taskkill /PID /T /F`
for owned process trees; POSIX uses owned process groups with a bounded TERM/KILL
sequence. Shutdown during a pending spawn cannot trigger a new fallback child.

Python selection is `JARVIS_PYTHON_BIN`, then project `.venv/Scripts/python.exe`,
then `python` on Windows; POSIX retains `.venv/bin/python`, `python3.11`, `python3`.
The override is a single executable path, including spaces if needed. Use the
project venv to ensure requirements are installed. Spawn errors ENOENT/EACCES try
the next candidate; a launched interpreter missing dependencies fails visibly.
All backend entry points now use the repository root as cwd, so relative
DB/profile/runtime overrides are resolved consistently there.

Optional PowerShell overrides (process environment only; `.env` is not auto-loaded):

```powershell
$env:JARVIS_PYTHON_BIN = (Resolve-Path .venv/Scripts/python.exe).Path
$env:JARVIS_RUNTIME_DIR = Join-Path $PWD 'runtime'
```

Start with default local ports. `JARVIS_AGENT_HOST/PORT` also feed Vite's API target
unless explicit `VITE_JARVIS_AGENT_HOST/PORT` values exist. Ollama health/start uses
`JARVIS_OLLAMA_HOST/PORT` or `OLLAMA_HOST`; if customized, the existing stored
`ollama_base_url` setting must match. Unreachable remote Ollama endpoints are not
replaced by an unrelated local server. No settings or personal databases are reset.

Use text input with voice mode/replies off. Existing macOS voice-list/TTS and native
tool endpoints may report errors on Windows; this PR does not port or enable them.
See [startup evidence and limits](architecture/windows-core-startup.md).

## 1. macOS prerequisites

Run from a normal terminal with Homebrew installed:

```bash
brew install python@3.11 node@22 ollama ffmpeg whisper-cpp portaudio libsndfile
export PATH="$(brew --prefix node@22)/bin:$PATH"
python3.11 --version
node --version
npm --version
```

Use Python 3.11 and Node 22, not whichever unrelated interpreter happens to be
first on `PATH`. With nvm already installed, `nvm install` / `nvm use` at the
repository root reads `.nvmrc`; no new Node version manager is required.
The Homebrew/app-launch instructions require real macOS verification; passing
Linux CI alone does not verify Homebrew, macOS permissions, or Apple Silicon audio.

## 2. Install project dependencies

From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r apps/agent/requirements.txt -r requirements-dev.txt
python -m pip check
npm ci
```

Always use `python -m pip` / `python -m pytest` from this environment. `pytest` was
not part of the original runtime requirements; the development requirements are
needed to run the documented tests. `npm ci` installs the checked-in lockfile
without intentionally updating dependencies. Change manifests and regenerate the
root lockfile together only in an explicitly justified dependency change.

Linux users running the same headless checks also need the audio shared libraries:

```bash
sudo apt-get update
sudo apt-get install --yes --no-install-recommends libportaudio2 libsndfile1
```

CI sets `ELECTRON_SKIP_BINARY_DOWNLOAD=1` only for static typecheck/build jobs.
Do not set it for normal desktop development: Electron needs its binary to run.
No LLM, Whisper/Piper model, microphone, AppleScript service, or running backend is
required by the current automated test suite.

## 3. Optional environment overrides

The Python configuration reads process environment variables. The root npm
commands do not automatically load `.env`. Defaults are sufficient for the
baseline. To customize them, copy the example only when no local file exists:

```bash
# Run this copy only for a new setup; do not overwrite an existing .env.
cp -n .env.example .env
# Edit and review your own .env before sourcing it.
set -a
source .env
set +a
export JARVIS_PYTHON_BIN="$PWD/.venv/bin/python"
```

The example leaves `JARVIS_PYTHON_BIN` unset so discovery prefers the project venv;
an existing explicit `python3.11` override remains valid. `source` executes shell syntax:
load only your own trusted file, never an unreviewed downloaded environment file.
Do not commit `.env`, credentials, recordings, models, or personal database files.
YJ2-00 does not change environment defaults or automatically apply the example.

Keep the baseline ports: agent `127.0.0.1:8787`, Ollama `127.0.0.1:11434`, and Vite
`5173`. The shared launcher waits for HTTP readiness before opening the desktop.

## 4. Models and application startup (macOS only)

For interactive use, start Ollama in a separate terminal unless already running:

```bash
ollama serve
```

In the project terminal, download the model selected by the existing setup and
its STT model:

```bash
ollama pull qwen2.5:3b-instruct
./scripts/download-whisper-model.sh ggml-small.bin
```

For Piper, obtain a compatible voice `.onnx` file and its matching `.onnx.json`
configuration, keep them in `runtime/models/`, and configure the absolute model
path in the existing Settings UI. Model downloads are not CI steps. The existing
macOS `say` TTS option remains available; neither voice backend is changed here.

```bash
npm run dev
```

This starts the existing Ollama runner, agent, and Electron/Vite desktop. The
Ollama runner reuses a server already responding on the default port. Stop the
development stack with Ctrl-C; an independently started Ollama server remains
owned by its original terminal/service.

Useful existing commands:

```bash
npm run dev:agent         # Agent only, no reload
npm run dev:agent:reload  # Agent only, with reload
npm run dev:desktop      # Desktop only; requires a running agent/Ollama for use
```

Use the existing macOS permission prompts for microphone and automation access.
Never disable safety controls or bypass tool approvals to make a smoke test pass.

## 5. Run the same checks as CI

From the repository root, with `.venv` active and dependencies installed:

```bash
python -m pip check
python -m pytest -q
python -m ruff check apps/agent/jarvis_agent tests
npm run test:startup
npm run typecheck
node --check apps/desktop/electron/main.cjs
node --check apps/desktop/electron/preload.cjs
npm run build
```

`tests/conftest.py` adds `apps/agent` to the import path. `pytest.ini` keeps discovery
inside `tests/` and rejects unknown configuration/markers. Existing tests are not
skipped or rewritten. Added repository tests detect drift between the duplicate
Python runtime manifests and between npm workspace manifests and the lockfile.

Ruff intentionally enables only `E9`, `F63`, `F7`, and `F82`: syntax, undefined
names, and selected correctness checks. This is not a full style/lint audit;
formatting, unused-import cleanup, and broader lint rules are separate work.
`npm run typecheck` uses the existing desktop `tsconfig.json` without weakening or
broadening it. Imported shared types are included; Electron CommonJS files get
syntax checks, not full TypeScript checking. `npm run build` is the existing Vite
renderer build producing `apps/desktop/dist`; it does not package/sign a macOS
application or launch Electron.

## 6. CI and review evidence

`.github/workflows/ci.yml` retains four Ubuntu jobs: `python-tests`, `python-lint`,
`desktop-typecheck`, and `desktop-build`, and adds `windows-python-tests` plus
`windows-desktop-checks`. All six fail on check failures.
They run for every PR targeting `main`, for pushes to `main`, and manual dispatch.
No path filters or `continue-on-error` hide failures. Actions are SHA-pinned,
checkout credentials are not persisted, and workflow permissions are read-only.
Windows jobs use native PowerShell and separate validation steps so a later
command cannot mask an earlier nonzero exit code. Both OS jobs run the complete
Python suite; no Windows-only skips, deselection or xfails were introduced.
Both Python jobs also run the Node 22 startup tests, including a real temporary
backend/SQLite session and owned process-tree cleanup with and without reload.
These tests install no models and launch no GUI.

A successful job proves only its actual commands. Inspect the final PR head's
check results and logs; never infer a pass from a workflow file existing. Consult
[CONTRIBUTING.md](../CONTRIBUTING.md) for the separate branch-protection limitation
and the mandatory external-review stop gate.

## 7. Manual macOS smoke checklist — not automated

Record actual results, platform, and any skipped scenario in the PR. Never mark
these as passed based solely on the Linux jobs:

- Launch the desktop and exchange one text message with local Ollama.
- Request opening an app and confirm the existing approval is still required.
- Read/list a supported item, then create a disposable reminder only after the
  existing confirmation flow. Remove the test reminder manually afterward.
- Test microphone -> STT -> text response -> selected TTS; check wake-word gating.
- Confirm a destructive/system-critical request is denied without execution.

Multi-step plans, trust changes, persistent STT, memory/routines V2, and a UI
redesign are not baseline smoke scenarios; those features belong to later steps.
No performance benchmark or end-to-end macOS result is implied by YJ2-00 CI.

## Troubleshooting and local data

If imports or `pytest` are missing, verify `which python` points into `.venv` and
reinstall both requirements files. If `npm ci` reports a lock mismatch, do not
replace it with an unreviewed dependency update to silence CI. If audio libraries
are missing, check the platform prerequisites before changing Python versions.
If STT/TTS fails interactively, check the configured binary, model/config files,
and permissions; do not treat helper unit tests as audio backend validation.

Keep the existing `runtime/jarvis.db`, profile, and model files. This step contains
no database migration and does not run the profile-regeneration script. Review
`scripts/apply_jarvis_profile.sh` before deliberately using it: it regenerates the
profile rather than serving as a required CI/bootstrap command. Database backups
should be made with the application stopped or with SQLite's backup facilities.
Reverting the infrastructure PR must not delete personal runtime data.
