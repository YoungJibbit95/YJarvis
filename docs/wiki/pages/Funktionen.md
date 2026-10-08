# Aktuelle Funktionen nach Kategorien

Stand dieser Einordnung ist der fachlich geprüfte Commit in der Fußzeile.
[Roadmap]({{WIKI}}/Roadmap) beschreibt zukünftige Funktionen separat.

| Kategorie | Aktueller Inhalt | Status / Grenze |
|---|---|---|
| Gespräch | lokale Ollama-Antworten, Sitzungen, Nachrichtenhistorie, Streaming, deterministische Antworten | aktiver Legacy-Pfad; Ollama/Modell erforderlich |
| Desktop | Electron/React, responsive Anwendungshülle, Navigation, Tokens/Primitive | integriert; große Legacy-UI-Verantwortlichkeiten bleiben |
| Einrichtung | Readiness-Anzeige, erster Setup-Zugang, erneuter Check | integriert, lesend; keine Installation |
| Modelle | kuratierter Offline-Katalog und Kategorienbrowser | integriert, beschreibend; keine Auswahl/Activation/Downloads |
| Hardware | OS, Architektur, CPU-Anzahl, RAM, Runtime-Speicher | integriert, lesend; keine Performance-Bewertung |
| Windows-Grafikadapter | DXGI-Beschreibungen, dedizierter Speicher, Shared-Memory-Limit, Klassifikation | integriert, lesend; kein Nachweis verfügbarer KI-Beschleunigung |
| Sprache | Mikrofonsegmentierung, Whisper-STT, Piper/`say`-TTS, Text-only, Echo-Unterdrückung | Legacy; macOS-Pfad, Windows-Audio unbestätigt |
| Apps/Browser | URL/App-Öffnen, Raycast öffnen/Kommandos | native Legacy-macOS-Tools mit Freigabe |
| Zwischenablage | Text lesen und ersetzen | Legacy `pbpaste`/`pbcopy`; Windows noch nicht veröffentlicht |
| Produktivität | Erinnerungen, Kalender, Notizen, Mailentwurf, Nachrichten, Kontakte, Musik | AppleScript/macOS; keine Windows-Parität |
| Dateien | Text lesen, überschreiben, anhängen | Legacy mit erlaubten Pfaden; keine Windows-Mutationsfreigabe |
| Lernen | explizite Trigger, gespeicherte Einzelaktionen, Erfolgs-/Latenzstatistik | Legacy; keine allgemeinen autonomen Lernprozesse |
| Gedächtnis | lokale Gesprächshistorie und Kompaktierung/FTS-Kontext | Legacy; keine semantischen V2-Memory-Objekte |
| Freigaben | ausstehende Aktionen genehmigen/ablehnen; lokale Protokolle | Legacy; jedes Tool weiterhin mit Freigabe |
| Smart Home | Entitäten, lokale Zustandsänderung, UI/API | **Stub**, keine tatsächliche Home-Assistant-Anbindung |
| Persistenz | SQLite, sichere Baseline-Migration/Legacy-Adoption | integriert; neue Plan-/Trust-Tabellen nicht eingeführt |
| V2-Verträge | Turn, Action, Plan, PolicyDecision, Observation, typed ToolSpec/Inputs/Outputs | isolierte Domain-Verträge; kein neuer Produktions-Wire-Vertrag |
| V2-Runtime | semantischer Katalog, Runtime-Kernel, explizite Provider-Registry | isoliert; keine Auto-Discovery, Timeout-Enforcement oder Policy |
| Windows URL-Provider | typisierte HTTP(S)-Übergabe an `os.startfile` | isoliert; kein Browser-Ladebeweis, keine Chat-Freischaltung |

Mehr Details: [Chat/Desktop]({{WIKI}}/Chat-und-Desktop),
[Tools]({{WIKI}}/Tools-und-Integrationen), [Sprache]({{WIKI}}/Sprache-und-Audio),
[Gedächtnis]({{WIKI}}/Gedaechtnis-und-Routinen), [Architektur]({{WIKI}}/Architektur).
„Implementiert“ belegt Quellcode, keine durch diesen Dokumentationszyklus
ausgeführte native Integration.
