# Windows installer support

Explicitly authorized by the user on 2026-10-08 as a separate packaging step.
This supersedes the previous packaging exclusion for this step only. No subsequent
provider, policy, planner, voice or migration step is authorized.
The user subsequently expanded this cycle to fix installed Ollama reachability,
check download sources and add a custom macOS-style titlebar without the native
Electron menu. These are part of the requested installed desktop experience.

## Build and install

On native Windows x64, with Node 22 and Python 3.11:

```powershell
npm ci
.\.venv\Scripts\python.exe -m pip install -r apps/agent/requirements.txt -r packaging/requirements.txt
npm run test:packaging
npm run dist:win
npm run test:packaged-backend
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke-windows-installer.ps1
```

Create the project venv first if needed (see `docs/development.md`). The build
selects a Python 3.11 interpreter with PyInstaller from the existing startup
candidate order. Dependencies are installed at build time, never during app launch.
Outputs are ignored under `build/` and `release/windows/`.

Run `release/windows/YJarvis-0.1.0-windows-x64-setup.exe`. The assisted NSIS
installer installs for the current user, lets you choose a directory and creates
Start Menu and desktop shortcuts. The default per-user install does not require administrator privileges,
launch the app after installation, publish a release or enable automatic updates.
The installer is currently unsigned; Windows may show an unknown-publisher warning.

Python, FastAPI and backend runtime libraries are bundled with PyInstaller in an
external resource directory. Installed users do not need Python, Node, npm or a
source checkout. Ollama and downloaded models remain separate prerequisites for
chat. On packaged launch the app reuses a healthy Ollama server or starts
`ollama serve` and waits for readiness. Only its own server is stopped on quit.
Discovery uses `JARVIS_OLLAMA_BIN`, PATH, then the standard Windows installation
under `%LOCALAPPDATA%/Programs/Ollama/ollama.exe`. Missing Ollama leaves the
setup screen accessible. This step does not establish Windows audio or native-tool parity.

## Runtime boundary and data

Installed Electron starts `resources/agent/jarvis-agent.exe` directly with the
existing owned-process cleanup. Missing/crashing backends cause a visible error
and app exit; there is no fallback to a system Python or Vite server. Startup
waits for backend health. External backend ownership remains supported through
`JARVIS_BACKEND_MANAGED=external` on the default loopback endpoint.

The packaged renderer uses the secure standard `app://yjarvis` origin with local
assets, fetch and WebSocket support. Path resolution rejects requests outside
the renderer directory. FastAPI allows this exact CORS origin alongside the two
existing development origins; arbitrary `null` origins are not allowed.

Packaged UI and backend use `127.0.0.1:8787`. Build-time Vite endpoint overrides
and process-level agent host/port overrides are deliberately normalized in this
packaging path. Development endpoint configuration is unchanged.

Default writable data lives under Electron's `%APPDATA%/YJarvis/runtime`, outside
installation files: SQLite, profile, model/audio/TTS directories. Explicit
`JARVIS_RUNTIME_DIR`, `JARVIS_DB_PATH`, `JARVIS_PROFILE_PATH` overrides are retained.
The packaged project root is the user-data directory, not the source checkout.
No personal source-checkout data, secrets or models are included in the installer.
Existing development data is not copied or reset. To reuse it, stop the developer
agent first and explicitly configure the runtime/database/profile paths.

Updates use the same app identity and user-data location. Uninstall preserves
user data. Roll back by uninstalling this build and reinstalling an earlier build;
do not delete the user-data directory. This step adds no schema migration.

## Verification and limits

`npm run test:packaging` tests path containment, frozen-process arguments, data
placement, explicit overrides, external ownership and spawn failure behavior.
`npm run test:packaged-backend` starts the actual frozen executable with disposable
data, verifies health, CORS, session creation, settings, setup status, WebSocket,
restart persistence and owned process cleanup. It requires port 8787 to be free
and never uses the personal database. CI builds the NSIS installer on Windows
and verifies silent installation into a unique temporary directory (including
spaces), installed EXE/backend/ASAR hashes, installed backend startup, and silent
uninstallation. The installer smoke refuses to replace an existing YJarvis
installation. CI uploads only the setup EXE as an artifact; it does not publish a release.

Interactive install/launch/update/uninstall, SmartScreen, Ollama generation,
microphone and audio behavior require manual smoke checks. macOS packaging is
not introduced or claimed tested. Existing development startup stays available.

Build-only dependencies: electron-builder 26.15.3, PyInstaller 6.22.3. Their
transitive graph follows the npm lockfile and Python packaging requirements;
Python transitives are not fully locked, matching the existing baseline.

The frozen EXE rejects Python CLI arguments (such as `-m piper`) rather than
starting another agent from a legacy CLI fallback. Optional Piper API/audio
behavior still requires its own manual validation; no voice support is claimed.

The local npm audit reported 25 findings in the complete development graph
(1 low, 11 moderate, 11 high, 2 critical), including legacy Electron/Vite and
concurrently dependencies and moderate builder transitives. Existing locked
package versions were preserved. Dependency/runtime upgrades and signing need
a separate reviewed step before a broadly distributed release.

## Window chrome and endpoint check

The native Electron menu is removed. Desktop windows use a draggable custom
titlebar with accessible close/minimize/maximize controls styled as macOS traffic
lights. Double-clicking the titlebar toggles maximization. The preload exposes
only those three commands; main accepts them only from the trusted top-level
renderer. Browser-only development retains the existing page layout.

On 2026-10-08 the checkout's catalog pages, Whisper/Piper model file URLs,
Node archive, whisper.cpp release archive and WinGet source were reachable.
The Ollama catalog page rejects HEAD (405) but GET returns 200; the configured
Qwen model manifest on the Ollama registry returns 200. No broken source URL was
found and no model was downloaded during the check. The catalog remains a
read-only browser: it has no model-download API to repair or implicitly enable.
