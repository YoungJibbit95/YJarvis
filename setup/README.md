# YJarvis-Grundinstallation ohne Modelle

Diese Skripte richten die Werkzeuge und Projektabhängigkeiten für einen vorhandenen
YJarvis-Checkout ein. Danach wählst und lädst du die Modelle separat.
Dieser eigenständige Setup-Schritt wurde am 2026-10-08 vom Nutzer beauftragt;
er setzt keinen weiteren V2-Provider- oder Audio-Migrationsschritt um.

## Schnellstart

Im Repository ausführen. Die Installationsskripte finden den Repo-Pfad auch dann,
wenn du sie aus einem anderen Verzeichnis startest.

| Plattform | Installation | Nur Vorschau, keine Installation |
| --- | --- | --- |
| Windows 11 x64 | `setup\windows.bat` (auch per Doppelklick) | `powershell -NoProfile -ExecutionPolicy Bypass -File setup\windows.ps1 -DryRun` |
| macOS, Apple Silicon / Intel | `bash setup/macos.sh` | `bash setup/macos.sh --dry-run` |
| Linux x64 / arm64 | `bash setup/linux.sh` | `bash setup/linux.sh --dry-run` |

Die Vorschau zeigt den Ablauf; sie prüft nicht, ob alle Werkzeuge bereits vorhanden sind.
Internet und freier Speicherplatz sind für Paketdownloads nötig. Starte macOS/Linux
als normaler Benutzer; Systempakete fragen bei Bedarf nach Administratorrechten.
Windows kann UAC-Dialoge für einzelne Installationen anzeigen.

## Was installiert wird

- **Git**, **Python 3.11**, **Node.js 22 mit npm**, **Ollama**, **FFmpeg**.
- **whisper.cpp / whisper-cli**, ohne STT-Modell.
- Die vorhandenen Python-Runtime- und Entwicklungsabhängigkeiten in **`.venv`**,
  einschließlich **Piper**, FastAPI, sounddevice/soundfile, pytest und Ruff.
- Die JavaScript-Abhängigkeiten aus dem vorhandenen Lockfile per **`npm ci`**,
  einschließlich Electron. Es wird kein Paket-Installer für YJarvis gebaut.
- Die benötigten Audio-Bibliotheken auf macOS/Linux; die VC++ Runtime auf Windows,
  falls sie für die nativen Binärdateien fehlt.

Die Versionen der Projektumgebung werden gegen `.python-version` und `.nvmrc`
geprüft. Eine vorhandene kompatible `.venv` wird weiterverwendet. Bei einer
unvollständigen oder inkompatiblen `.venv` bricht das Setup ab und lässt sie bestehen.
Fehlgeschlagene Installationen liefern einen Fehlercode und stoppen die nachfolgenden
Schritte. Nach Beheben des Fehlers kannst du das Skript erneut starten.

## Plattformdetails

**Windows:** Die `.bat` startet Windows PowerShell. Ihr ExecutionPolicy-Bypass gilt
nur für diesen Prozess und verändert keine dauerhafte Richtlinie. Fehlende
Systemwerkzeuge werden mit WinGet aus dessen `winget`-Quelle installiert:
`Git.Git`, `Python.Python.3.11`, `Ollama.Ollama`, `Gyan.FFmpeg` und bei Bedarf
`Microsoft.VCRedist.2015+.x64`. Wenn WinGet fehlt, installiere Microsofts
[App Installer](https://aka.ms/getwinget) und starte erneut.
Eine passende Node-22-Installation wird verwendet; sonst landet das offizielle
Node-22.23.3-ZIP in `.setup-tools/node`. Eine andere globale Node-Version wird dadurch
nicht ersetzt. Die CPU-Version von whisper.cpp **v1.8.3** landet mit ihren DLLs in
`.setup-tools/whisper`. Beide Archive werden vor dem Entpacken gegen hinterlegte
SHA256-Werte geprüft. Bash, WSL, Visual Studio und CUDA sind nicht erforderlich.

**macOS:** Das Skript verwendet Homebrew oder installiert es über dessen offiziellen
Installer. Apple Command Line Tools und Homebrew können interaktive Systemdialoge
oder ein Passwort verlangen. Installiert werden `git python@3.11 node@22 ollama
ffmpeg whisper.cpp portaudio libsndfile`. Die versionierten Python-/Node-Formeln
werden für das Setup und die spätere Aktivierung ausdrücklich in den PATH genommen.
Es werden keine zusätzlichen Homebrew-Services eingerichtet.

**Linux:** Automatisch unterstützt werden **Debian/Ubuntu mit apt**, **Fedora mit dnf**
und **Arch mit pacman**, jeweils mit glibc. Andere Distributionen werden vor der
Installation mit einer erklärenden Fehlermeldung abgewiesen; dort sind die manuellen
Schritte im [Entwicklungsleitfaden](../docs/development.md) der Ausgangspunkt.
Fedora verwendet `ffmpeg-free` aus den offiziellen Repositories.
**Arch führt `pacman -Syu` aus, also ein vollständiges Systemupdate**, um eine
nicht unterstützte Teilaktualisierung zu vermeiden.
Fehlt ein Python 3.11 mit venv/ensurepip, installiert das Skript uv und dessen
verwaltetes Python in `.setup-tools`. Ein unpassendes Node wird durch das aktuelle
offizielle Node-22-Archiv in `.setup-tools/node` ergänzt; die heruntergeladene
SHA256-Liste wird vor dem Entpacken geprüft. whisper.cpp v1.8.3 wird lokal per
CMake als CPU-CLI gebaut, sofern `whisper-cli` noch nicht vorhanden ist.
Ollama wird aus dem in der offiziellen Anleitung beschriebenen CLI-Archiv in
`.setup-tools/ollama` installiert, sofern es noch nicht vorhanden ist. Die Struktur
mit `bin` und `lib` bleibt erhalten. Es wird kein systemd-Dienst eingerichtet und
kein GPU-Treiber installiert. Das Archiv enthält Ollamas Runtime-Bibliotheken;
zusätzliche Hardware-Konfiguration oder ROCm-Pakete bleiben ein späterer Schritt.

Keine LLM-, Whisper- oder Piper-Stimmenmodelle werden heruntergeladen. Das Setup
startet YJarvis nicht, ruft keine Modell-Pull-Befehle auf und verändert weder `.env`
noch Profile, Datenbanken oder bestehende Einstellungen. Paketinstaller können
ihre eigenen üblichen PATH-/Autostart-Einträge anlegen. Die Hilfsskripte verändern
keine Shell-Profile und setzen selbst keinen dauerhaften PATH.

## Danach: Umgebung und Modelle

Öffne ein Terminal im Repo. Unter Windows kannst du eine PowerShell mit einer nur
für diese Sitzung geltenden Richtlinie öffnen und die lokalen Werkzeuge aktivieren:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass
. .\setup\activate.ps1
node --version
& $env:JARVIS_PYTHON_BIN --version
```

Unter macOS/Linux in Bash:

```bash
source setup/activate.sh
node --version
"$JARVIS_PYTHON_BIN" --version
```

Die Aktivierung gilt für dieses Terminal und seine Kindprozesse. Sie ergänzt
Node/whisper und die `.venv` im PATH und setzt `JARVIS_PYTHON_BIN`; sie startet nichts.
Wenn du einen anderen Prozess zum Starten verwendest, aktiviere dort die Umgebung
ebenfalls oder konfiguriere die absoluten Binärpfade selbst.

Nun kannst du Ollama-Modelle selbst auswählen und später herunterladen. Whisper-
und Piper-Stimmenmodelle sowie ihre Pfade werden ebenfalls separat eingerichtet;
siehe [Entwicklungsleitfaden](../docs/development.md). Erst danach:

```text
npm run dev           # Windows/macOS: Entwicklungsapp
npm run dev:agent     # Linux: Headless-Backend
```

Ohne Modelle ist die Grundinstallation möglich, aber noch keine LLM-Antwort oder
Sprachverarbeitung. Windows Text/Core bleibt der verifizierte Windows-Umfang;
installierte Audio-Werkzeuge bedeuten keine verifizierte Windows-Sprachwiedergabe
oder native macOS-Tool-Parität. Linux bleibt ein Headless-/CI-Ziel.

## Prüfung, Grenzen und Entfernen

`install_dependencies.py` führt `pip check` aus und verlangt Python 3.11 / Node 22.
Die vollständigen Test-/Build-Befehle stehen im [Entwicklungsleitfaden](../docs/development.md).
Automatisierte Tests prüfen Vorschau, Shell-Syntax, Versionskonflikte, Fehlerabbruch
und den Erhalt bestehender Umgebungen. Sie führen keine Systempaketinstallation
aus und beweisen keine frische Installation auf jeder Distribution oder Audio-Parität.

Ein Checkout mit Leerzeichen im Pfad wird unterstützt. Verwende für vollständiges
Electron-Setup kein `ELECTRON_SKIP_BINARY_DOWNLOAD=1`; diese CI-Option spart das
Electron-Binary aus. Systempaketquellen, Netzwerke, Unternehmensrichtlinien oder
UAC können eine Installation verhindern. Fehler erscheinen direkt im Terminal.
Ein übermäßig langer Windows-PATH kann npm-Unterprozesse an der
[`cmd.exe`-Grenze von 8191 Zeichen](https://learn.microsoft.com/en-us/troubleshoot/windows-client/shell-experience/command-line-string-limitation)
scheitern lassen. Die Aktivierung vermeidet doppelte Einträge;
bei weiterhin überlangem PATH verwende ein Terminal mit einem bereinigten
Sitzungs-PATH. Die Setup-Skripte bereinigen deinen dauerhaften System-PATH nicht.
Wird ein lokales Tool-Archiv nur teilweise entpackt, bleibt es zur Prüfung erhalten;
verwende einen neuen Checkout oder entferne nach Prüfung nur dessen betroffenen
Ordner unter `.setup-tools` und starte erneut.

`.setup-tools`, `.venv` und `node_modules` sind lokale, ignorierte Installationsausgaben.
Zum Zurücknehmen der Repo-Änderung genügt ein Revert dieses Setup-Commits.
Bereits installierte Systempakete entfernt ein Git-Revert nicht; deinstalliere sie
bei Bedarf mit dem jeweiligen Paketmanager. Lösche dabei keine persönlichen Daten
unter `runtime`, keine Modelle und keine vorher vorhandenen Installationen.

Offizielle Quellen, geprüft am 2026-10-08:

- [Microsoft WinGet install](https://learn.microsoft.com/en-us/windows/package-manager/winget/install),
  [Paketmanifeste](https://github.com/microsoft/winget-pkgs).
- [Node-22-Downloads und Prüfsummen](https://nodejs.org/dist/latest-v22.x/).
- [Homebrew-Installation](https://brew.sh/), [Node 22](https://formulae.brew.sh/formula/node@22).
- [Aktuelle whisper.cpp-Formel](https://github.com/Homebrew/homebrew-core/blob/main/Formula/w/whisper.cpp.rb).
- [Ollama für Windows](https://docs.ollama.com/windows), [Ollama für Linux](https://docs.ollama.com/linux).
- [uv-Installeroptionen](https://docs.astral.sh/uv/reference/installer/),
  [verwaltetes Python](https://docs.astral.sh/uv/guides/install-python/).
- [whisper.cpp v1.8.3](https://github.com/ggml-org/whisper.cpp/releases/tag/v1.8.3),
  [CMake-Build](https://github.com/ggml-org/whisper.cpp/blob/v1.8.3/README.md#quick-start).
