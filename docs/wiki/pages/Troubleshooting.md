# Troubleshooting

| Symptom | Prüfen | Nächster Schritt |
|---|---|---|
| Python fehlt | `py -3.11 --version` (Windows), `python3.11 --version` (macOS) | 3.11 installieren; einzelner venv-Pfad für `JARVIS_PYTHON_BIN` |
| Importfehler | Projekt-venv verwendet? `python -m pip check` | Dependencies in genau diesem Interpreter installieren |
| `npm.ps1` blockiert | PowerShell-Ausführungsrichtlinie | denselben Befehl als `npm.cmd` verwenden |
| Electron fehlt | wurde sein Binary-Download übersprungen? | normale `npm ci`-Installation; CI-Override nicht für GUI nutzen |
| Backend nicht erreichbar | `/health`, Launcher-Ausgabe, Host/Port | Portkonflikt/Interpreter prüfen; keine DB löschen |
| Ollama nicht erreichbar | `ollama list`, `/api/tags`, konfigurierter Endpunkt | vorhandenen Server starten; Settings/Launcher-Adressen angleichen |
| Chatmodell fehlt | `ollama list`, Modell-ID in Settings | genau dieses Modell separat laden |
| Setup `degraded` trotz Textantwort | STT-Datei, TTS `voice_unverified` | kann erwartbar sein; Readiness ist kein Audio-Smoke |
| STT fehlgeschlagen | Binary, Modellpfad, ffmpeg, CLI-Kompatibilität | Komponenten einzeln prüfen; Windows-Parität nicht voraussetzen |
| Keine Sprachantwort | Text-only, Engine, ONNX/JSON-Paar, Playback | auf macOS gezielt prüfen; Windows-Audio unbestätigt |
| Windows-Tool schlägt fehl | Legacy macOS-Aufruf? | Plattformstatus lesen; isolierter Provider ist nicht Chat-wired |
| Tool wartet | ausstehende Freigaben und Argumente | bewusst genehmigen/ablehnen; Safety nicht umgehen |
| Datei blockiert | erlaubte/kanonische Pfade und kritische Pfadregeln | legitimen Pfad korrekt konfigurieren; keine Blanket-Allow-Regel |
| Smart Home reagiert nur in UI | Stub-Provider | kein reales Gerätekommando erwarten |
| Changelog/Wiki veraltet | fachlicher SHA vs Git-Historie, Actions-Lauf | Sync-Fehler/Token prüfen; Texte bei Verhaltenänderung mitpflegen |

## Ungefährliche lokale Prüfungen

```powershell
Invoke-RestMethod http://127.0.0.1:8787/health
Invoke-RestMethod http://127.0.0.1:11434/api/tags
Invoke-RestMethod http://127.0.0.1:8787/v1/setup/status
.\.venv\Scripts\python.exe -m pip check
```

HTTP-Inventar/Health ist keine vollständige Inferenz-/GUI-/Audioprüfung.
Fehlerbericht: Plattform, Python/Node-Version, Quell-SHA, verwendeter Startbefehl,
betroffener Bereich, redigierter Fehler und minimale Reproduktion. Keine
persönliche DB, Transkripte, Credentials oder unredigierten Logs hochladen.

Ausgangspunkt: [Entwicklungsanleitung]({{SOURCE}}/docs/development.md).
