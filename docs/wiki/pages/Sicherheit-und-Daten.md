# Sicherheit und lokale Daten

## Aktuelle Regeln

Alle Legacy-Tool-Aktionen verlangen eine explizite Freigabe, auch gelernte
Trigger und lesende Tools. Die geplante progressive Trust-Policy ist nicht
aktiv. Pfadregeln beschränken Dateizugriff auf `allowed_paths`; kritische
Pfade/destruktive Inhalte werden zusätzlich geprüft.

Die Regeln stammen teilweise aus dem macOS/Unix-Kontext. Windows benötigt vor
breiter Mutation gesonderte Regeln für Laufwerkswurzeln, Windows/Program Files,
UNC, Groß-/Kleinschreibung und Junctions/Reparse Points. Keine Windows-Parität
aus Python-Portabilität oder einem Windows-Testlauf ableiten.

Mailentwürfe und gesendete Nachrichten haben unterschiedliche Konsequenzen.
Clipboard, Kontakte, Notizen und Nachrichten können personenbezogene Inhalte
enthalten. Freigaben, Tool-Ergebnisse und Nachrichten liegen lokal in der DB;
eine Freigabe ist keine dauerhafte globale Trust-Regel.

## Datenorte

Standardmäßig: `runtime/jarvis.db`, `runtime/jarvis_profile.json`,
`runtime/models/`, `runtime/audio/`, `runtime/tts/`.
Ollama verwaltet seine eigenen Modelle separat. Overrides siehe [Setup]({{WIKI}}/Setup).
Die Datenbank kann Sitzungen, Nachrichten, Memory, gelernte Kommandos,
Einstellungen, Freigaben und Tool-Protokolle enthalten. Keine pauschale
Verschlüsselungszusage ableiten; Dateien wie persönliche lokale Daten schützen.

„Local-first“ heißt: der konfigurierte Ollama-Endpunkt und Modelle sind lokal
betreibbar. Modelldownloads brauchen Netzwerk; geöffnete URLs und Nachrichten
haben externe Effekte. Ein selbst konfigurierter Remote-Ollama-Endpunkt ist
ebenfalls nicht vollständig lokal. Keine absolute Offline-/Cloudfreiheit für
jede mögliche Konfiguration behaupten.

## Sicherung und Wiederherstellung

Vor App-Updates/Migrationen sichern. Am einfachsten den Agenten vollständig
stoppen und DB/Profile kopieren; während eines laufenden WAL-Schreibbetriebs
nicht nur die einzelne `.db` blind kopieren. Alternativ die SQLite-Backup-API
für eine konsistente Live-Sicherung verwenden. Modelle separat sichern oder
ihre reproduzierbaren Quellen notieren. Wiederherstellung zuerst mit einer
Kopie prüfen; keine produktive persönliche DB als Testfixture nutzen.

Migrationsinfrastruktur bewahrt Legacy-Daten und protokolliert Schema-Versionen.
Ein fehlgeschlagener Start ist kein Anlass, persönliche Daten zu löschen.
DB/Logs/Audio/Modelle und `.env` gehören nicht in Git oder Debug-Uploads.

Quellen: [Safety]({{SOURCE}}/apps/agent/jarvis_agent/safety.py),
[Tool-Pfadprüfung]({{SOURCE}}/apps/agent/jarvis_agent/tools/security.py),
[Migrationsnachweise]({{SOURCE}}/docs/architecture/persistence-migrations.md),
[CONTRIBUTING]({{SOURCE}}/CONTRIBUTING.md).
