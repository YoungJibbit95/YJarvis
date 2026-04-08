# Jarvis Local v1

Lokaler Jarvis fuer macOS (M1/M2) ohne Cloud-Zugriffe.

## Stack

- Python FastAPI Agent (`apps/agent`)
- Electron + React UI (`apps/desktop`)
- SQLite fuer Sessions, Memory, Settings (`runtime/jarvis.db`)
- Ollama als lokaler LLM Runtime
- Whisper.cpp fuer Speech-to-Text
- Piper fuer Text-to-Speech

## Voraussetzungen (macOS)

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

## LLM Setup

```bash
ollama serve
ollama pull qwen2.5:3b-instruct
```

## Whisper Modell

Empfohlen fuer bessere Erkennung: `ggml-small.bin` (lokal, whisper.cpp).

```bash
./scripts/download-whisper-model.sh ggml-small.bin
```

Optional (schneller, aber ungenauer): `ggml-base.bin`.

## Piper Modell

Setze in der UI unter `Settings -> Piper Modellpfad` den absoluten Pfad zu deinem lokalen Piper Modell.

## Start

```bash
npm install
npm run dev
```

`npm run dev` startet Ollama + Agent + Desktop zusammen (Root-Orchestrierung).
Wenn du nur den Agent starten willst:

```bash
npm run dev:agent
```

Optional mit Hot-Reload:

```bash
npm run dev:agent:reload
```

## Sprachmodus

- `Sprachmodus starten`: einmal klicken, dann bleibt Mikrofon aktiv.
- Jarvis transkribiert lokal und sendet erkannte Sprache automatisch nach kurzer Sprechpause.
- Voice-Gating aktiv: Sprachkommandos werden nur gesendet, wenn der Satz mit `Jarvis` beginnt (`Jarvis ...`).
- Standard: Jarvis antwortet per Sprachausgabe ueber `piper` (komplett lokal).
- Im Settings-Tab werden verfuegbare `say`-Stimmen automatisch geladen, falls du optional auf `tts_engine=say` umstellst.
- Mit `Text only` wird Auto-Sprachausgabe deaktiviert (manuelles `Vorlesen` bleibt moeglich).
- STT setzt einen Jarvis-Kontextprompt und korrigiert haeufige Wakeword-Fehler (`jobs` -> `Jarvis`) in typischen Anrede-Saetzen.
- STT hat zusaetzliche Halluzinationsfilter fuer kurze Artefakt-Ausgaben (z. B. `swr 2020`) und verwirft diese.
- STT normalisiert haeufige bairische Kurzformen (`i`, `ned/net`, `koa/koan`, `des`) fuer robustere Kommandos.
- Kurze Alltagsphrasen wie `danke`/`hallo` werden lokal als Schnellantwort behandelt (ohne extra LLM-Roundtrip).
- WebSocket verbindet sich bei Unterbrechung automatisch neu (Backoff-Reconnect).
- Echo-Schutz aktiv: waehrend TTS wird Voice-Input kurz unterdrueckt, damit Lautsprecher-Ausgabe nicht als neue Eingabe zurueckkommt.
- Persona ist auf `Sir` als direkte Anrede ausgerichtet (statt `mein Herr`) und auf einen freundlicheren Ton.
- Fuer die Audioausgabe wird `Sir` intern auf die konfigurierte Lautung gemappt (Default `Sör`), damit es nicht wie `sier` klingt.
- Die TTS-Nachlauf-Sperre ist kurz gehalten, damit du direkt nach Jarvis wieder sprechen kannst.
- Wakeword-only (`Jarvis`) wird nicht als Aufgabe gesendet; sprich den Auftrag direkt danach.

## Audio-Temp Cleanup

- Upload-, STT- und TTS-Tempdateien werden nach Verarbeitung automatisch geloescht.
- Zusaetzlich begrenzt ein Wartungsjob alte Artefakte in `runtime/audio` und `runtime/tts`.
- Optional per Env anpassbar:
  - `JARVIS_AUDIO_TMP_KEEP` (Default `30`)
  - `JARVIS_TTS_TMP_KEEP` (Default `20`)
  - `JARVIS_TMP_MAX_AGE_SECONDS` (Default `43200`, also 12h)

## Jarvis Persona + Sicherheitsprofil

Profilskript ausfuehren (erstellt/ueberschreibt `runtime/jarvis_profile.json`):

```bash
./scripts/apply_jarvis_profile.sh
```

Das Profil wird pro Anfrage geladen und ist damit ab der naechsten Agent-Anfrage aktiv.

Das Profil steuert:
- Jarvis-Sprachstil (deutsch, praezise, technisch)
- Blockliste fuer destruktive Requests (z. B. "loesch alle daten", "rm -rf /")
- Harte Sperre fuer systemkritische Pfade (`/System`, `/usr`, `/etc`, ...)
- Inhaltsfilter fuer gefaehrliche Befehlsmuster in Datei-Schreibaktionen
- Pflicht-Bestaetigung fuer sicherheitsrelevante, aber nicht direkt destruktive Requests

## API Uebersicht

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

## Sicherheitsmodell

- Tool-Ausfuehrung nur nach expliziter Freigabe.
- Datei-Schreiboperationen nur in `allowed_paths`.
- Zusaetzliche Hard-Block-Regeln gegen systemkritische/zerstoererische Requests.
- Kritische, fragwuerdige Requests (z. B. sudo/keychain/launchctl) werden erst nach expliziter Chat-Bestaetigung weiterbearbeitet.
- Komplette Tool-Runs + Approvals werden lokal in SQLite protokolliert.

## Tests

```bash
source .venv/bin/activate
pytest -q
```

## Hinweise

- Wenn `python3.11` nicht gefunden wird, setze `JARVIS_PYTHON_BIN` beim Start der Desktop-App.
- Wenn TTS fehlschlaegt, pruefe `tts_engine`, `tts_model_path` und ob `piper` im PATH ist.
- Piper wird standardmaessig bevorzugt ueber die Python-API mit Model-Cache genutzt (schnellerer Start bei Folgesaetzen); fallback auf CLI bleibt aktiv.
- Wenn STT fehlschlaegt, pruefe `whisper_binary`, `whisper_model_path` und `ffmpeg`.
- Fuer schnellere Antworten: `JARVIS_OLLAMA_KEEP_ALIVE=30m`, `JARVIS_ENABLE_TOOL_PLANNER=0`, kleinere `JARVIS_HISTORY_LIMIT`/`JARVIS_MEMORY_LIMIT`.
- Fuer schnellere Streaming-Textausgabe kannst du Token-Batching tunen:
  - `JARVIS_TOKEN_FLUSH_INTERVAL_MS` (Default `20`)
  - `JARVIS_TOKEN_FLUSH_MIN_CHARS` (Default `8`)
- Fuer weniger monotone Piper-Ausgabe kannst du die Prosody per Env feinjustieren:
  - `JARVIS_PIPER_LENGTH_SCALE`
  - `JARVIS_PIPER_NOISE_SCALE`
  - `JARVIS_PIPER_NOISE_W_SCALE`
  - `JARVIS_PIPER_SENTENCE_SILENCE`
  - `JARVIS_PIPER_VOLUME`
  - `JARVIS_PIPER_USE_PYTHON_API` (Default `1`, empfohlen fuer geringere Latenz)
- Fuer STT-Qualitaet/Empfindlichkeit kannst du Whisper-Decoding justieren:
  - `JARVIS_WHISPER_BEAM_SIZE`
  - `JARVIS_WHISPER_BEST_OF`
  - `JARVIS_WHISPER_NO_SPEECH_THOLD`
  - `JARVIS_WHISPER_ENTROPY_THOLD`
  - `JARVIS_WHISPER_LOGPROB_THOLD`
- Alternative: `tts_engine=say` mit natuerlicheren lokalen Stimmen wie `Anna`, `Flo (Deutsch (Deutschland))`, `Eddy (Deutsch (Deutschland))`.
- Bei `tts_engine=say` kannst du die Geschwindigkeit ueber `say_rate_wpm` steuern (ca. `200`-`260` sinnvoll).
- `tts_sir_pronunciation` steuert die Audio-Lautung fuer das Wort `Sir` (z. B. `Sör`).
