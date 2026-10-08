# Setup und Konfiguration

## Erste Einrichtung und Readiness

Die Oberfläche zeigt den Einrichtungsstatus und ermöglicht einen erneuten
Check. `GET /v1/setup/status` ist lesend. Es installiert nichts und führt keine
Tools, Audioprüfungen oder Modellgenerierung aus.

| Zustand | Bedeutung |
|---|---|
| `needs_setup` | Chatmodell fehlt oder Ollama ist nicht erreichbar |
| `ready` | alle Komponenten als verfügbar eingestuft |
| `degraded` | Chatmodell vorhanden, mindestens eine Audio-Komponente nicht bestätigt |
| `error` | Chat-Konfiguration/Antwort fehlerhaft oder unbekannt |

STT prüft nur, ob die konfigurierte/default GGML-Datei eine nichtleere reguläre
Datei ist. TTS bleibt selbst bei vorhandener Piper-Datei `unknown/voice_unverified`,
solange Audio nicht verifiziert wird. Im geprüften Stand ist `ready` deshalb
kein realistisches Ergebnis des normalen Piper-Checks. `degraded` kann für
Textbetrieb erwartbar sein. Das Chatmodell wird im Ollama-Inventar (`/api/tags`)
gesucht; Inventarpräsenz beweist weder ausreichenden RAM noch erfolgreiche Inferenz.

## Modellkatalog und Hardware

`GET /v1/setup/models` liefert einen kleinen kuratierten Offline-Katalog:

- Qwen2.5 3B Instruct für Chat, Ollama-ID `qwen2.5:3b-instruct`.
- Whisper Small für STT, Runtime-Datei `ggml-small.bin`.
- Thorsten Deutsch für Piper-TTS, `de_DE-thorsten-medium`.

Die UI kann Kategorien/Einträge durchsuchen und Quellen, Downloadhinweise und
Lizenzangaben anzeigen. Sie **lädt, installiert oder aktiviert** kein Modell.
Beim Thorsten-Eintrag ist die Gewichts-Lizenz unbekannt; CC0 betrifft dort den
Datensatz. Kategorien und Qualitätslabels sind keine Hardware-Empfehlung.

`GET /v1/setup/hardware` zeigt OS, Architektur, logische CPU-Anzahl, gesamten RAM
und freien Speicher im Runtime-Verzeichnis. Fehlende Werte bleiben unbekannt.
Die separate Route `GET /v1/setup/accelerators` und die UI-Unteransicht
„Grafik / Beschleuniger“ zeigen auf Windows native DXGI-Adapterbeschreibungen,
dedizierten Videospeicher, das Shared-System-Memory-Limit und die native
Klassifikation `hardware`/`software`/`unknown`. Shared Memory ist eine Obergrenze,
kein freier/reservierter RAM und kein garantierter Inferenzspeicher; Werte nicht
addieren. `available` kann eine gültige leere Liste bedeuten; Fehler werden
`unknown`, andere Plattformen `unsupported`. Dies aktiviert kein CUDA/DirectML,
belegt keine Modelltauglichkeit und erzeugt keine Benchmarks/Leistungsprofile.

## Persistierte Settings und Prozessumgebung

Settings werden über `GET/PUT /v1/settings` in SQLite gespeichert. Dazu gehören
Chatmodell/Ollama-Adresse, TTS-Engine/Modell/Stimme, Whisper-Binary/Modell und
`allowed_paths`. Umgebungsvariablen steuern Start und weitere Runtime-Parameter.
Eine `.env`-Datei wird von den npm-Startbefehlen **nicht automatisch geladen**.

| Variable | Vorgabe / Zweck |
|---|---|
| `JARVIS_AGENT_HOST`, `JARVIS_AGENT_PORT` | `127.0.0.1`, `8787` |
| `JARVIS_PYTHON_BIN` | einzelner Python-Executable-Pfad; venv wird sonst bevorzugt |
| `JARVIS_RUNTIME_DIR` | standardmäßig `<repository>/runtime` |
| `JARVIS_DB_PATH` | standardmäßig `<runtime>/jarvis.db` |
| `WHISPER_MODEL` | standardmäßig `<runtime>/models/ggml-small.bin` |
| `JARVIS_PROFILE_PATH` | standardmäßig `<runtime>/jarvis_profile.json` |
| `JARVIS_BACKEND_MANAGED` | `external` schützt einen extern verwalteten Backend-Prozess |
| `JARVIS_OLLAMA_HOST/PORT`, `OLLAMA_HOST` | Launcher-Endpunkt; gespeichertes `ollama_base_url` muss dazu passen |
| `VITE_JARVIS_AGENT_HOST/PORT` | expliziter Vite-API-Zieloverride |
| `JARVIS_OLLAMA_KEEP_ALIVE` | Beispielprofil `30m` |
| `JARVIS_ENABLE_TOOL_PLANNER` | Beispielprofil `0`; Legacy-Planner separat schaltbar |
| `JARVIS_HISTORY_LIMIT`, `JARVIS_MEMORY_LIMIT` | Kontextbegrenzung; Beispielprofil `6` / `1` |
| `JARVIS_TOKEN_FLUSH_INTERVAL_MS/MIN_CHARS` | Stream-Bündelung; `20` ms / `8` Zeichen im Beispiel |
| `JARVIS_AUDIO_TMP_KEEP`, `JARVIS_TTS_TMP_KEEP` | Tempfile-Begrenzung; `30` / `20` im Beispiel |
| `JARVIS_TMP_MAX_AGE_SECONDS` | Tempfile-Alter; `43200` im Beispiel |

Weitere Whisper-Decoding-/Piper-Prosodieparameter stehen in
[.env.example]({{SOURCE}}/.env.example) und
[audio.py]({{SOURCE}}/apps/agent/jarvis_agent/audio.py).
Beispielwerte sind keine Aussage darüber, dass eine kopierte `.env` wirksam ist.
Auf Windows Overrides explizit über `$env:NAME = 'Wert'` setzen. Die API nicht
ohne eine separat geprüfte Sicherheitskonfiguration ins Netzwerk exponieren.

Quellen: [Readiness]({{SOURCE}}/docs/architecture/setup-readiness.md),
[Katalog]({{SOURCE}}/docs/architecture/model-catalog.md),
[Browser]({{SOURCE}}/docs/architecture/model-catalog-browser.md),
[Hardware]({{SOURCE}}/docs/architecture/baseline-hardware-profile.md),
[Windows-Adapter]({{SOURCE}}/docs/architecture/windows-accelerator-profile.md).
