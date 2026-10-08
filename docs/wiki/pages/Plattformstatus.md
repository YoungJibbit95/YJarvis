# Plattformstatus

„Code vorhanden“, „CI geprüft“ und „nativ manuell verifiziert“ sind verschiedene
Nachweise. Diese Tabelle beschreibt den Quellstand; sie ist keine neue manuelle
Integrationstestbescheinigung.

| Bereich | Windows 11 x64 | macOS Apple Silicon | Linux |
|---|---|---|---|
| Entwicklungsstart | nativer Text/Core-Launcher ohne Bash/WSL | gemeinsamer Launcher, Legacy unterstützt | Headless-Backend-/Startup-CI |
| FastAPI/SQLite | Core + Migration/Startup-CI | gemeinsamer Core | Core-/Migration-CI |
| Ollama-Textchat | vorgesehen und dokumentiert; echter Modell-Smoke separat | Legacy vorhanden | modellfreie CI beweist keine Generierung |
| Settings/Streaming | gemeinsamer Text/Core-Pfad | gemeinsamer Pfad | statische/Core-Checks |
| Setup/Katalog/Hardwarebasis | integriert, lesend | integriert, plattformbedingte Werte | integriert, Headless-Tests |
| Grafikadapter-Abfrage | integrierte DXGI-Beschreibungen, keine Beschleunigungszusage | ausdrücklich unsupported | ausdrücklich unsupported |
| URL öffnen | isolierter Provider gemergt, nicht im Chat verdrahtet | aktiver Legacy-`open`-Pfad | kein veröffentlichter nativer Provider |
| Clipboard lesen | isolierter Win32-Provider gemergt, nicht im Chat verdrahtet | Legacy `pbpaste` | kein veröffentlichter nativer Provider |
| Apps/Clipboard schreiben/Raycast | keine produktive Provider-Parität | Legacy; Raycast optional | keine Paritätszusage |
| Kalender/Notizen/Mail etc. | keine native Implementierungszusage | Legacy-AppleScript | keine native Implementierung |
| Dateimutationen | keine Freigabe breiter Windows-Mutation | Legacy-Pfadregeln | bestehender Python-Code, keine Desktop-Zusage |
| STT/TTS/Playback | native Audioparität unbestätigt | Legacy vorhanden; manuell zu testen | Importtests benötigen Bibliotheken; keine Audio-Zusage |
| Paketiertes Release | noch geplant | noch geplant | kein Desktop-Releaseziel |

Der Legacy-Katalog enthält noch macOS-Tools auch auf anderen Hosts. Das
Addendum verlangt künftig, unverfügbare Fähigkeiten aus der Planner-Verfügbarkeit
auszuschließen; der isolierte semantische Provider-Katalog setzt diese Migration
noch nicht im aktiven Legacy-Planner um. Startup-Verträglichkeit darf deshalb
nicht als verfügbare Tool-Parität gelesen werden.

Vor V2-Beta vorgesehen: Desktop/Backend, SQLite, Ollama, Settings, Streaming,
URL/Apps/Clipboard, lokale STT/TTS/Wiedergabe, plattformsichere Dateien und
ActionPlan/Policy/Memory/Routines. Native Produktivitätsintegrationen können
optional oder ausdrücklich unsupported bleiben. Raycast bleibt ein macOS-Extra.

Quelle: [Cross-Platform-Addendum]({{SOURCE}}/docs/architecture/02_WINDOWS_CROSS_PLATFORM_ARCHITECTURE_ADDENDUM.md).
