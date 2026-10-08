# Release Notes: fachliche Einordnung

Die Version in den Manifesten bleibt `0.1.0`. Die folgenden Gruppen sind
gemergte Entwicklungszyklen, keine erfundenen SemVer-Releases. Vollständige
Commitbeschreibungen und Dateiänderungen: [Changelog]({{WIKI}}/Changelog).

## 2026-10-08

| Schritt / PR | Änderung | Nutzerwirkung / Grenze |
|---|---|---|
| YJUX-00B · #14 | responsive AppShell und Navigation extrahiert | integrierte Hülle; restliche Legacy-UI bleibt |
| YJ2-05B1 · #13 | typisierte Capability-Inputs | isolierte Validierungsverträge; Wire/DB/Planner unverändert |
| YJ2-05B2 · #16 | typisierte Outputs | isolierte Verträge; keine Legacy-ToolResult-Konvertierung |
| YJUX-01A · #15 | Setup-Readiness und erster Einrichtungszugang | lesende Checks; keine Installation oder Audioausführung |
| YJ2-05B3 · #18 | semantischer Katalog und Legacy-Lookup getrennt | bekannt ist nicht verfügbar |
| YJUX-02A · #17 | kuratierter Offline-Modellkatalog | Quellen/Lizenzen; keine Auswahl/Downloads |
| YJ2-05C1 · #19 | semantischer Runtime-Kernel | injizierte Provider, Ein-/Ausgabevalidierung; isoliert |
| YJUX-02B · #20 | read-only Modellbrowser | Kategorien/Details; aktiviert kein Modell |
| YJ2-05C2 · #21 | explizite Provider-Registry/Verfügbarkeit | keine Auto-Discovery oder Produktionsverdrahtung |
| YJUX-02C1 · #22 | Basis-Hardwareprofil | OS/Architektur/CPU/RAM/Storage, keine GPU/Benchmarks |
| YJW-01A · #23 | Windows HTTP(S)-URL-Provider | `os.startfile` ohne Shell; nicht im Chat aktiviert |
| YJUX-02C2A · #24 | native Windows-DXGI-Adapter im Setup | dedizierte Speicherwerte/Shared-Memory-Obergrenze, keine Benchmarks oder Modelltauglichkeit |

## 2026-10-07

YJ2-03 (#5) extrahierte eine TurnEngine-Shell unter Erhalt des Legacy-Verhaltens.
YJW-00A (#6) ergänzte echte Windows-Automationschecks für Python/Core/Desktop.
YJW-00B (#7) führte gemeinsame native Windows-/macOS-Text/Core-Launcher ein.
YJ2-04A (#8) isolierte deterministische Routingstufen; YJ2-04B (#9) den
Legacy-Planneradapter. YJW-00B.1 (#10) korrigierte Ollama-Health/Ownership:
eine bloße TCP-Antwort wird nicht als passender Ollama-Server behandelt.
YJ2-05A (#11) ergänzte inerte semantische ToolSpecs/Legacy-Metadaten.
YJUX-00A (#12) legte UI-Tokens und native Primitive an.
Keine dieser Extraktionen schaltete progressive Policy oder Mehrschritt-Pläne frei.

## 2026-10-06

YJ2-00 (#1): CI, Entwicklungsanleitung und Review-Guardrails.
YJ2-01 (#2/#3 und zugehörige Branch-Commits): Domain-V2-Verträge mit
Validierungs-/Isolationsnachweisen. Die Historie enthält beide Integrationspfade;
der Changelog verschweigt keine Merge-/Branch-Commits.
YJ2-02 (#4): atomarer Migrationsrunner und sichere Legacy-DB-Adoption,
mit Nachweisen zu Datenerhalt, Fehler-Rollback und SQLite/WAL.

## 2026-04-08 bis 2026-04-09: Legacy-Fundament

Lokaler FastAPI-/Electron-/React-Assistent, SQLite, Ollama, Whisper/Piper,
Text-/Voice-Oberfläche und explizite Freigaben. Anschließend robustere
Sprachaufnahme/UI-Reaktivität, breitere macOS-Automation, gelernte Trigger,
Raycast und lokale Zuverlässigkeits-/Latenzstatistik. README-/Badge-/Sprachhinweise
wurden separat geändert; sie stellen keine neuen Laufzeitfähigkeiten dar.
Architekturbaseline: `dea0e9e6a266584e9c8efaf53dd82138aecbd662`.

## Noch nicht veröffentlicht

Lokale Clipboard-Arbeit ist nicht Teil des geprüften Stands.
Neue Freigaben nur vom Nutzer; siehe [Roadmap]({{WIKI}}/Roadmap).
Prüfungen und Integrationsbelege müssen pro PR gelesen werden; diese Seite
behauptet keine pauschalen manuellen Audio-/macOS-Testergebnisse.

PR-Nachweise: [gemergte PRs](https://github.com/YoungJibbit95/YJarvis/pulls?q=is%3Apr+is%3Amerged).
