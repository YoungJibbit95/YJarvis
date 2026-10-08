# Aktuelle API

Standard: `http://127.0.0.1:8787`, WebSocket `ws://127.0.0.1:8787`.
Im laufenden Agenten liefert `/docs` die FastAPI-OpenAPI-Ansicht, `/openapi.json`
deren Schema. Aktuelle produktive DTOs stehen in
[schemas.py]({{SOURCE}}/apps/agent/jarvis_agent/schemas.py);
Domain-V2-Verträge ersetzen sie noch nicht. Dies ist eine lokale
Entwicklungs-API, kein bestätigter abgesicherter öffentlicher Dienst.

| Methode / Route | Zweck | Wirkung / Grenze |
|---|---|---|
| `GET /health` | Backend antwortet | prüft keine Modellgenerierung |
| `POST /v1/sessions` | Sitzung erzeugen | persistiert Sitzung |
| `GET /v1/sessions/{session_id}/messages` | Historie lesen | bekannte Session erforderlich |
| `POST /v1/chat` | Text einreichen | Legacy-Routing/Antwort/Freigabe |
| `WS /v1/ws/{session_id}` | Streaming-Ereignisse | Legacy-Protokoll, kein V2-Event-Enforcement |
| `GET /v1/approvals/pending` | ausstehende Freigaben | lesend |
| `POST /v1/approvals/{approval_id}` | genehmigen/ablehnen | Genehmigung kann echte Tool-Effekte auslösen |
| `GET /v1/settings` | Settings lesen | lokale Konfiguration |
| `PUT /v1/settings` | Settings ändern | persistiert; kein automatischer Modelldownload |
| `POST /v1/audio/transcribe` | Multipart-Audio transkribieren | Binary/Model/ffmpeg erforderlich |
| `GET /v1/audio/voices` | vorhandene Stimmen abfragen | Legacy `say`-/macOS-Annahmen |
| `POST /v1/audio/speak` | TTS erzeugen | Engine/Modell/Playback-Grenzen |
| `GET /v1/smarthome/entities` | lokale Stub-Entitäten | keine echte Hardwareabfrage |
| `POST /v1/smarthome/call` | Stub-Zustand ändern | kein echtes Home Assistant |
| `GET /v1/setup/status` | Readiness | Modellinventar/Dateien, keine Inferenz |
| `GET /v1/setup/models` | Offline-Katalog | beschreibend, keine Installation |
| `GET /v1/setup/hardware` | Basiswerte | keine Beschleuniger/Benchmarks |
| `GET /v1/setup/accelerators` | native Windows-DXGI-Adapter | getrennt vom Basisprofil; andere OS unsupported, keine Performancezusage |

## Minimaler Text-Smoke auf Windows

Bei laufendem Agenten und konfiguriertem Ollama-Modell:

```powershell
$session = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/v1/sessions
$body = @{ session_id = $session.session_id; message = 'Hallo Jarvis' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/v1/chat -ContentType 'application/json' -Body $body
```

Die endgültige Antwort kann über WebSocket-Ereignisse kommen; ein erfolgreicher
Chat-HTTP-Aufruf alleine beweist keinen vollständigen Antwortstream.
Tool-Freigaben nicht als generischen Smoke-Test automatisch genehmigen.

Quellen: [main.py]({{SOURCE}}/apps/agent/jarvis_agent/main.py),
[setup_api.py]({{SOURCE}}/apps/agent/jarvis_agent/setup_api.py),
[Setup]({{WIKI}}/Setup).
