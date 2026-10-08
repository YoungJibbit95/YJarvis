# YJarvis Local v1

![Repository Views](https://komarev.com/ghpvc/?username=YoungJibbit95&repo=YJarvis&label=Repository%20Views&color=0e75b6&style=flat)
[![GitHub Stars](https://img.shields.io/github/stars/YoungJibbit95/YJarvis?style=flat)](https://github.com/YoungJibbit95/YJarvis/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/YoungJibbit95/YJarvis?style=flat)](https://github.com/YoungJibbit95/YJarvis/network/members)
[![Last Commit](https://img.shields.io/github/last-commit/YoungJibbit95/YJarvis?style=flat)](https://github.com/YoungJibbit95/YJarvis/commits/main)

A fully local desktop assistant for macOS (Apple Silicon). No cloud calls.
Keep in mind that this is a german project for now, i will add support for english later.
But you should be able to change it yourself, for that you need to download a english piper model and replace the piper model path with your downloaded model. Put TTS models in `/runtime/models/`. Then set your models name in TTS Voice in settings and it should work.

For now, YJarvis sadly doesnt sound like the real version, if someone is able to find a voice model of him in german or english, please make a pull request. I want to add that as soon as possible but for now he only acts like Jarvis.

## Stack

- Python FastAPI agent (`apps/agent`)
- Electron + React desktop UI (`apps/desktop`)
- SQLite for sessions, memory, settings (`runtime/jarvis.db`)
- Ollama for local LLM runtime
- whisper.cpp for speech-to-text (STT)
- Piper for text-to-speech (TTS)
- Raycast Deeplink integration (optional, local)

## Development and V2 migration

See [the development guide](docs/development.md) for exact setup/check commands,
CI coverage limits, environment loading, and the manual macOS checklist.
The [V2 architecture and browser-agent master prompt](docs/architecture/README.md)
is the migration source of truth. Follow [CONTRIBUTING.md](CONTRIBUTING.md): one
approved step, one PR, external review, then explicit user authorization to proceed.
YJ2-00 adds infrastructure only; the product behavior described below is unchanged.

## Automatic base setup (no models)

The [setup folder](setup/README.md) installs the base tools and project dependencies:

- Windows 11 x64: run `setup\windows.bat`.
- macOS: run `bash setup/macos.sh`.
- Linux (Debian/Ubuntu, Fedora, Arch): run `bash setup/linux.sh`.

Ollama, FFmpeg, whisper.cpp and Piper are included; model/voice downloads and
application startup happen afterward. See the setup guide for permissions,
the preview mode and activating the installed tools. Installing tools does not
add native Windows/Linux audio or automation support to the application.

## Requirements (macOS)

```bash
brew install python@3.11 node@22 ollama ffmpeg whisper.cpp portaudio libsndfile
export PATH="$(brew --prefix node@22)/bin:$PATH"
```

## Python Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r apps/agent/requirements.txt -r requirements-dev.txt
```

## Local Model Setup

### 1) LLM (Ollama)

In a separate terminal (unless Ollama is already running):

```bash
ollama serve
```

Then, in the project terminal:

```bash
ollama pull qwen2.5:3b-instruct
```

### 2) Whisper model (recommended: `ggml-small.bin`)

```bash
./scripts/download-whisper-model.sh ggml-small.bin
```

Optional (faster, less accurate): `ggml-base.bin`.

### 3) Piper voice model

Set the absolute model path in UI: `Settings -> Piper model path`.

## Run

```bash
npm ci
npm run dev
```

`npm run dev` starts Ollama + Agent + Desktop together.

Agent only:

```bash
npm run dev:agent
```

Agent with hot reload:

```bash
npm run dev:agent:reload
```

## Voice Mode

- Click once to start voice mode, click again to stop.
- Audio is transcribed locally and auto-sent after a short pause.
- Voice command gating is enabled: commands are only sent if the sentence starts with `Jarvis ...`.
- Wake-word only input (for example just `Jarvis`) is ignored.
- `Text only` disables automatic spoken replies.
- Echo suppression is active to avoid re-capturing speaker output.

## Learning Mode

Jarvis can learn custom triggers and optimize tool decisions from local success/latency stats.

- Teach: `/learn "abendroutine" => oeffne raycast`
- List learned triggers: `/learn-list`
- Remove learned trigger: `/unlearn "abendroutine"`

Notes:

- Learned commands are stored locally in SQLite.
- Every learned action still requires explicit approval before execution.
- Tool routing is adapted over time based on local execution reliability and speed.

## Safety Model

- Every tool action requires explicit approval.
- File writes are restricted to configured `allowed_paths`.
- Hard block rules reject destructive/system-critical requests.
- Sensitive requests require explicit confirmation before execution.
- Tool runs and approvals are logged locally in SQLite.

## Safety/Profile Script

Run this to (re)generate `runtime/jarvis_profile.json`:

```bash
./scripts/apply_jarvis_profile.sh
```

The profile is loaded per request and becomes effective on the next request.

## API Overview

- `POST /v1/sessions`
- `POST /v1/chat`
- `GET /v1/sessions/{session_id}/messages`
- `GET /v1/approvals/pending`
- `POST /v1/approvals/{id}`
- `GET /v1/settings`
- `PUT /v1/settings`
- `POST /v1/audio/transcribe`
- `GET /v1/audio/voices`
- `POST /v1/audio/speak`
- `GET /v1/smarthome/entities`
- `POST /v1/smarthome/call`
- `WS /v1/ws/{session_id}`

## Audio Temp Cleanup

- Upload/STT/TTS temp files are deleted after processing.
- A maintenance cleanup also limits old artifacts in `runtime/audio` and `runtime/tts`.

Env tuning:

- `JARVIS_AUDIO_TMP_KEEP` (default `30`)
- `JARVIS_TTS_TMP_KEEP` (default `20`)
- `JARVIS_TMP_MAX_AGE_SECONDS` (default `43200` = 12h)

## Performance Tuning

Recommended baseline:

- `JARVIS_OLLAMA_KEEP_ALIVE=30m`
- `JARVIS_ENABLE_TOOL_PLANNER=0`
- Lower `JARVIS_HISTORY_LIMIT` and `JARVIS_MEMORY_LIMIT`

Streaming responsiveness:

- `JARVIS_TOKEN_FLUSH_INTERVAL_MS` (default `20`)
- `JARVIS_TOKEN_FLUSH_MIN_CHARS` (default `8`)

Whisper decoding:

- `JARVIS_WHISPER_BEAM_SIZE`
- `JARVIS_WHISPER_BEST_OF`
- `JARVIS_WHISPER_NO_SPEECH_THOLD`
- `JARVIS_WHISPER_ENTROPY_THOLD`
- `JARVIS_WHISPER_LOGPROB_THOLD`

Piper prosody:

- `JARVIS_PIPER_LENGTH_SCALE`
- `JARVIS_PIPER_NOISE_SCALE`
- `JARVIS_PIPER_NOISE_W_SCALE`
- `JARVIS_PIPER_SENTENCE_SILENCE`
- `JARVIS_PIPER_VOLUME`
- `JARVIS_PIPER_USE_PYTHON_API` (default `1`)

## Testing

```bash
source .venv/bin/activate
python -m pip check
python -m pytest -q
python -m ruff check apps/agent/jarvis_agent tests
npm run typecheck
npm run build
```

The four CI checks are `python-tests`, `python-lint`, `desktop-typecheck`, and
`desktop-build`. They test the existing Python suite and static desktop build on
Linux, not interactive macOS audio/automation or a packaged Electron app.

## Troubleshooting

- If `python3.11` is not found, set `JARVIS_PYTHON_BIN`.
- If TTS fails, check `tts_engine`, `tts_model_path`, and `piper` availability.
- If STT fails, check `whisper_binary`, `whisper_model_path`, and `ffmpeg`.
- Optional alternative TTS engine: `tts_engine=say`.
