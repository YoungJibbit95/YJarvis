# Local development and baseline checks

## What this baseline covers

YJ2-00 added CI and review guardrails; YJ2-01 through YJ2-03 added inert domain
contracts, migration infrastructure and an orchestration extraction. YJW-00A
adds a native Windows automated baseline. Windows 11 x64 is the primary current
development target; macOS Apple Silicon remains first-class, with the existing
macOS runtime setup below. Automated checks run on Ubuntu 24.04 and the x64
`windows-2025` runner with Python **3.11.x** (`.python-version`) and Node.js **22.x**
(`.nvmrc`). Patch versions are logged by CI. This does not claim Windows desktop
startup or broader Python/Node support.

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

These commands test the platform-neutral core and static desktop code. The root
`npm run dev`, managed backend discovery and native tool/audio providers are still
legacy runtime paths and are **not** made Windows-ready by YJW-00A. See the
[Windows baseline note](architecture/windows-test-ci-baseline.md) for the three
test fixes, retained assertions and verification limits.

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

The example sets `JARVIS_PYTHON_BIN=python3.11`; the explicit override above keeps
the agent on the project virtual environment. `source` executes shell syntax:
load only your own trusted file, never an unreviewed downloaded environment file.
Do not commit `.env`, credentials, recordings, models, or personal database files.
YJ2-00 does not change environment defaults or automatically apply the example.

Keep the baseline ports: agent `127.0.0.1:8787`, Ollama `127.0.0.1:11434`, and Vite
`5173`. The existing root development command waits on the default agent/Ollama
ports; coordinated custom-port support is not part of this step.

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
