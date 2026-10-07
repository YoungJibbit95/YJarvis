# YJarvis V2 — Windows / Cross-Platform Architecture Addendum

**Primary desktop target:** Windows 11 x64  
**Retained first-class target:** macOS Apple Silicon  
**Headless CI target:** Linux

YJarvis is no longer defined as a macOS-only assistant.

> **YJarvis is a private, local-first personal operating agent for Windows and macOS. The core agent is platform-neutral; OS integration is provided by explicit platform providers.**

## Cross-platform invariants

### Core is OS-neutral
These layers must not call AppleScript, PowerShell, Win32, `open`, `pbcopy`,
`afplay`, `say`, `cmd.exe`, or platform-specific filesystem rules:

- `domain/`
- `orchestration/`
- `planning/`
- `policy/`
- `memory/`
- `routines/`
- generic persistence core
- generic LLM clients

### Capability names stay semantic
Use:
- `apps.open`
- `url.open`
- `clipboard.read`
- `clipboard.write`

Do not put the OS into Action domain capability names.

### Unsupported means unavailable
If a capability has no provider on the host:
- do not expose it to the planner as available;
- do not fake success;
- do not silently map to an unrelated tool;
- return/represent explicit unavailability.

Raycast may remain macOS-only.

### Safety before parity
Never enable a Windows mutating capability before equivalent Windows safety
rules exist. Current Unix/macOS critical-path prefixes do not protect Windows.

### Domain contracts stay shared
Do not fork Action/ActionPlan/PolicyDecision/Observation by OS.

## Capability parity tiers

### Tier A — required on Windows and macOS before V2 beta
- desktop launch
- FastAPI backend
- SQLite persistence/migrations
- local Ollama chat
- settings
- WebSocket streaming
- URL open
- app open
- clipboard read/write
- local STT
- local TTS
- audio playback
- file read/write only after platform-safe policy
- ActionPlan/policy/execution core
- memory/routines core

### Tier B — native productivity integrations
macOS currently has AppleScript implementations for reminders/calendar/notes/mail/messages/contacts/music.

Windows may use:
1. a safe local provider;
2. an optional integration provider; or
3. explicit unsupported status.

Do not introduce mandatory cloud services just for checkbox parity.

### Tier C — OS-specific extras
Raycast is a macOS extra. A future Windows launcher integration may be separate.

## Provider architecture

Target after ToolSpec V2:

```text
semantic capability
        |
Tool Registry / Capability Catalog
        |
Platform Provider Resolver
     /        \
 macOS        Windows
 provider     provider
```

Possible shape:

```text
jarvis_agent/
  platform/
    detection.py
    availability.py
    paths.py

  tools/
    providers/
      macos/
      windows/
```

Do not create unused interfaces ahead of need.

## Native Windows development bootstrap

A Windows developer must eventually be able to use native PowerShell without WSL.

Required concepts:
- Python 3.11
- Node 22
- npm
- Ollama for Windows
- ffmpeg on PATH
- supported whisper.cpp runtime/executable
- Piper where verified
- Electron

When implementing docs, verify exact install commands against current official upstream instructions.

### Replace POSIX npm launch syntax
Prefer small Node `.mjs` or Python launch helpers:
- explicit environment maps;
- `child_process.spawn`;
- `path.delimiter`;
- no `VAR=value command`;
- no `${VAR:-fallback}`;
- no mandatory Bash.

Avoid adding `cross-env` if a small existing-runtime helper is clearer.

### Ollama runner
Cross-platform runner should:
- health-check configured Ollama endpoint;
- reuse an already-running server;
- otherwise spawn `ollama serve`;
- preserve child ownership;
- work on Windows/macOS;
- not require `curl`.

### Whisper model downloader
Provide a platform-neutral helper or documented manual path. No Bash requirement.

### Profile generation
If profile regeneration remains supported, provide a platform-neutral replacement
for `apply_jarvis_profile.sh`.

## Electron backend process management

Support Windows interpreter discovery:
- explicit `JARVIS_PYTHON_BIN`;
- `.venv\Scripts\python.exe`;
- `python`;
- optionally Python launcher logic if correctly modeled as executable + args.

Keep macOS:
- explicit `JARVIS_PYTHON_BIN`;
- `.venv/bin/python`;
- appropriate python3 candidates.

Verify process termination on Windows; do not assume POSIX signal/process-group semantics.

## Audio architecture

Move toward explicit backends:

```python
SttBackend
TtsBackend
AudioPlaybackBackend
VoiceCatalogBackend  # optional
```

### STT
Whisper is conceptually cross-platform. Discovery must handle PATH, configured
binary, Windows executable suffix behavior and future persistent backend.

### TTS
Piper should be evaluated as the primary cross-platform local TTS path.
macOS `say` remains an optional macOS backend.
Windows SAPI is optional, not required for first Windows launch.

### Playback
`afplay` is macOS-only. Prefer a genuine cross-platform playback path.
The project already depends on `sounddevice`/`soundfile`; evaluate those before
adding another runtime dependency.

### Voice catalog
Do not treat `say` voices as a universal voice catalog. Engine/provider must be explicit.

## Tool provider strategy

### App / URL open
Current macOS `open` commands move behind a provider.
Windows implementation must avoid unsafe shell interpolation.

### Clipboard
Current `pbpaste`/`pbcopy` are macOS-only.
Windows clipboard content must not be concatenated into shell commands.

### AppleScript productivity tools
Keep them as macOS providers.
Do not delete macOS support while adding Windows.

### Raycast
Register only when available on macOS. Do not expose Raycast to Windows planner.

## Windows path safety

Before enabling broad Windows file mutation, policy must handle:
- system drive/root;
- Windows installation directory;
- Program Files;
- ProgramData;
- case-insensitive canonical comparison;
- drive normalization;
- UNC/network paths;
- symlinks/junctions/reparse points where relevant;
- allowed-path containment.

Use canonical path APIs, not scattered backslash string checks.

## Cross-platform CI

After Windows bootstrap, add real Windows signal:
- Python dependency install;
- relevant Python tests;
- `npm ci`;
- typecheck;
- renderer build;
- Electron entry-point syntax;
- backend import/startup health if feasible without models.

Retain Linux headless CI.

Retain automated macOS signal too. Because macOS Actions cost can be higher, choose
a deliberate lightweight required job or scheduled/manual integration workflow,
but do not silently let macOS become untested.

CI without models does not prove Ollama generation, microphone, STT performance,
TTS playback or OS automation. Maintain local smoke checklists for Windows and macOS.

## Packaging direction
Do not solve packaging inside the first Windows bootstrap unless required to launch.

Before beta:
- Windows packaged Electron path;
- macOS packaged Electron path;
- user data outside application files;
- safe upgrade/migration behavior;
- dual-platform smoke/upgrade validation.

## Definition of “startable on Windows” for the early bootstrap milestone
1. clone on Windows 11;
2. native Python venv;
3. `npm ci`;
4. locally installed Ollama;
5. start YJarvis without Bash/WSL;
6. Electron UI opens;
7. FastAPI backend healthy;
8. DB initializes/migrates;
9. settings work;
10. text chat reaches local Ollama in manual smoke;
11. unsupported macOS-native tools do not crash startup.

This does not yet mean every AppleScript capability has a Windows equivalent.

## Mandatory future review questions
1. Did this add an OS assumption to a core module?
2. Is platform-specific code behind a provider?
3. Does the planner see unavailable capabilities?
4. Did Windows support regress macOS?
5. Did macOS support force Windows to use Bash/Unix?
6. Are safety semantics equivalent before mutation is enabled?
7. Are behavior differences explicit?
8. Was each claimed platform result actually tested?
