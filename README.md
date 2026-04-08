# YJarvis Local v1

A fully local desktop assistant for macOS (Apple Silicon). No cloud calls.

## Stack

- Python FastAPI agent (`apps/agent`)
- Electron + React desktop UI (`apps/desktop`)
- SQLite for sessions, memory, settings (`runtime/jarvis.db`)
- Ollama for local LLM runtime
- whisper.cpp for speech-to-text (STT)
- Piper for text-to-speech (TTS)

## Requirements (macOS)

```bash
brew install python@3.11 ollama ffmpeg whisper-cpp portaudio
```

## Python Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r apps/agent/requirements.txt
```

## Local Model Setup

### 1) LLM (Ollama)

```bash
ollama serve
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
npm install
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
pytest -q
```

## Troubleshooting

- If `python3.11` is not found, set `JARVIS_PYTHON_BIN`.
- If TTS fails, check `tts_engine`, `tts_model_path`, and `piper` availability.
- If STT fails, check `whisper_binary`, `whisper_model_path`, and `ffmpeg`.
- Optional alternative TTS engine: `tts_engine=say`.
