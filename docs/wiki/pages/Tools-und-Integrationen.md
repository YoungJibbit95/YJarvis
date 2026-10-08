# Tools und Integrationen

Die aktive [Legacy-Registry]({{SOURCE}}/apps/agent/jarvis_agent/tools/registry.py)
registriert 18 Tools. Alle verlangen Freigabe. Die semantischen Namen im
[V2-Katalog]({{SOURCE}}/apps/agent/jarvis_agent/domain/capability_catalog.py)
sind Migrationsmetadaten; API-/DB-/Planner-Namen werden dadurch nicht umbenannt.

## Browser, Apps, Launcher, Zwischenablage

| Legacy-Name → semantischer Name | Wirkung | Voraussetzung / Grenze |
|---|---|---|
| `open_url` → `url.open` | HTTP(S)-URL im Browser öffnen | Legacy verwendet macOS `open` |
| `open_app` → `apps.open` | Anwendung nach Namen öffnen | macOS `open -a`; Ziel muss existieren |
| `raycast_open` → `raycast.open` | Raycast öffnen, optional mit Suche | Raycast installiert, macOS |
| `raycast_run_command` → `raycast.command.run` | Raycast-Erweiterung per Deeplink aufrufen | optional; Kommando kann externe Effekte haben |
| `clipboard_read` → `clipboard.read` | Clipboard-Text lesen | macOS `pbpaste`; kann sensible Inhalte enthalten |
| `clipboard_write` → `clipboard.write` | Clipboard-Text ersetzen | macOS `pbcopy`; aktueller Inhalt wird ersetzt |

Gemergtes Windows-Fundament: `WindowsUrlOpenProvider` nimmt nur die semantische
Capability `url.open` und validierte HTTP(S)-Eingaben an. Die native Grenze ist
`os.startfile`, ohne Shell-Interpolation. Die Rückgabe sagt lediglich, dass der
native Aufruf zurückkehrte; sie prüft weder Browserstart noch geladenen Inhalt.
Der Provider wird nicht produktiv registriert und nicht an den Planner angehängt.
Windows Clipboard/App-Provider und deren Adapter sind hier noch geplant.

## Produktivität und Kommunikation

| Legacy-Name → semantischer Name | Wirkung | Auswirkung |
|---|---|---|
| `reminder_create` → `reminders.create` | Erinnerung, optional Notizen/Fälligkeitszeit | schreibend |
| `reminder_list` → `reminders.list` | unvollständige Erinnerungen aus Liste | lesend |
| `calendar_create_event` → `calendar.events.create` | Kalenderereignis erstellen | schreibend |
| `calendar_list_events` → `calendar.events.list` | anstehende Ereignisse abfragen | lesend |
| `notes_create` → `notes.create` | Notiz und gegebenenfalls Zielordner erstellen | schreibend |
| `notes_search` → `notes.search` | Notizen nach Text/Ordner suchen | lesend |
| `mail_create_draft` → `mail.drafts.create` | E-Mail-Entwurf erstellen | sendet selbst keine E-Mail |
| `messages_send` → `messages.send` | Nachricht an Empfänger senden | tatsächlicher externer Effekt; vorher freigeben |
| `contacts_search` → `contacts.search` | Kontakte nach Namen suchen | personenbezogene Daten |
| `music_control` → `music.control` | Wiedergabe, Pause, nächster/vorheriger Titel | System-/App-Zustand |

Alle diese Implementierungen nutzen macOS/AppleScript und benötigte App-/OS-Rechte.
Beispiele natürlicher Eingaben sind keine Zusage, dass jede freie Formulierung
eindeutig erkannt wird. Vor einer Freigabe Ziel und Argumente prüfen.

## Dateien

| Legacy-Name → semantischer Name | Wirkung | Begrenzung |
|---|---|---|
| `file_read` → `files.read` | Textdatei lesen | `allowed_paths`, kritische Pfade; Ausgabe nach 6000 Zeichen gekürzt |
| `file_write` → `files.write` | `overwrite` oder `append`; Elternverzeichnis bei Bedarf anlegen | Pfad-/Inhaltsprüfung, Freigabe; Überschreiben kann Daten verlieren |

Die Python-Dateifunktionen existieren, aber die Legacy-Systempfadregeln sichern
keine pauschale Windows-Mutationsparität ab. Keine breite Windows-Dateiautomation
aktivieren, bevor dort kanonische Pfade, Laufwerke, UNC und Reparse Points
fachlich abgesichert sind. Keine Rollback-/Dry-Run-Zusage ableiten.

## Smart Home

`HomeAssistantStubProvider` liest Entitäten aus der lokalen DB und verändert
deren simulierten Zustand mit `toggle`, `turn_on` oder `turn_off`. Dies steuert
keine tatsächlichen Geräte und ist keine Home-Assistant-Verbindung.

Quellen: [System-Tools]({{SOURCE}}/apps/agent/jarvis_agent/tools/system_tools.py),
[AppleScript]({{SOURCE}}/apps/agent/jarvis_agent/tools/applescript_tools.py),
[Dateien]({{SOURCE}}/apps/agent/jarvis_agent/tools/file_tools.py),
[Stub]({{SOURCE}}/apps/agent/jarvis_agent/smarthome.py),
[Windows URL]({{SOURCE}}/docs/architecture/windows-url-provider.md).
