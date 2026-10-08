# YJarvis Wiki

YJarvis ist ein privater, lokal ausgerichteter Desktop-Assistent für deutsche
Text- und Sprachinteraktion. Der Agent nutzt FastAPI, SQLite und Ollama; die
Oberfläche nutzt Electron, React und TypeScript. Windows 11 x64 ist das primäre
aktuelle Ziel, macOS Apple Silicon bleibt ein eigenständiges Ziel. Linux dient
der automatisierten Headless-Prüfung.

## Einstieg

1. [Dependencies und Systemvoraussetzungen]({{WIKI}}/Dependencies) prüfen.
2. [Windows installieren]({{WIKI}}/Installation-Windows) oder
   [macOS installieren]({{WIKI}}/Installation-macOS).
3. [Setup und Modelle konfigurieren]({{WIKI}}/Setup).
4. [Aktuelle Funktionen]({{WIKI}}/Funktionen) und
   [Plattformgrenzen]({{WIKI}}/Plattformstatus) beachten.
5. Bei Problemen: [Troubleshooting]({{WIKI}}/Troubleshooting).

## Orientierung

| Bereich | Inhalt |
|---|---|
| [Dokumentationsindex]({{WIKI}}/YJarvis-Documentation-and-Wiki) | Alle technischen Seiten und Lesepfade |
| [Architektur]({{WIKI}}/Architektur) | Laufender Legacy-Pfad, isolierte V2-Bausteine und Zielarchitektur |
| [API]({{WIKI}}/API) | Aktuelle HTTP-, Audio-, Setup- und WebSocket-Schnittstellen |
| [Sicherheit und Daten]({{WIKI}}/Sicherheit-und-Daten) | Freigaben, lokale Speicherung und Sicherung |
| [Roadmap]({{WIKI}}/Roadmap) | Geplante Funktionen nach Kategorien und Migration |
| [Release Notes]({{WIKI}}/Release-Notes) | Fachliche Einordnung gemergter Änderungen |
| [Changelog]({{WIKI}}/Changelog) | Vollständige Commit-Nachweise mit Dateiänderungen |
| [Entwicklung]({{WIKI}}/Entwicklung) | Tests, Builds und externer Review-Prozess |
| [Dokumentationspflege]({{WIKI}}/Dokumentationspflege) | Quellen, Veröffentlichung und automatische Historie |

## So liest du den Funktionsstatus

- **Legacy implementiert:** Code ist im aktiven Anwendungspfad vorhanden;
  Betriebsfähigkeit hängt von OS, Modellen und Berechtigungen ab.
- **Integriert:** Der neue Baustein wird tatsächlich von der Anwendung verwendet.
- **Isoliert:** Gemergter, getesteter Baustein ohne Freischaltung in Chat/Planner.
- **Stub:** Oberfläche/API existiert, die echte Integration fehlt.
- **Geplant:** Architekturziel ohne veröffentlichte Implementierung.
- **Offen:** Ein PR oder lokale Arbeit ist noch kein veröffentlichter Stand.

Ein Katalogeintrag oder importierbarer Provider ist **keine** Verfügbarkeitszusage.
CI-Erfolg belegt die ausgeführten Checks, keine native Audio-/Automationsprüfung.
Die Fußzeile trennt den fachlich geprüften Stand von der automatisch erfassten
Git-Historie. Die Architektur ist ein Migrationsziel, kein Feature-Katalog des
laufenden Produkts.

Grundlage: [Entwicklungsanleitung]({{SOURCE}}/docs/development.md),
[Cross-Platform-Addendum]({{SOURCE}}/docs/architecture/02_WINDOWS_CROSS_PLATFORM_ARCHITECTURE_ADDENDUM.md).
