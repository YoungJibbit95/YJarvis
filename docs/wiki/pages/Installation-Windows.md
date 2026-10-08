# Installation auf Windows

Ziel dieses Guides ist die Entwicklungsinstallation für **Text/Core auf Windows
11 x64**. Es gibt hier keinen Installer für ein fertig paketiertes Release.
Audio und macOS-Automation haben separate Grenzen: [Plattformstatus]({{WIKI}}/Plattformstatus).

## 1. Voraussetzungen installieren

Python 3.11 über die [offizielle Windows-Anleitung](https://docs.python.org/3/using/windows.html)
installieren. Beim aktuellen Python Install Manager kann eine 3.11-Runtime
installiert werden; eine vorhandene 3.11-Installation genügt. Entscheidend ist:

```powershell
py -3.11 --version
```

**Node 22 x64** über den [offiziellen Download](https://nodejs.org/en/download)
wählen, anschließend PowerShell neu öffnen:

```powershell
node --version
npm --version
git --version
```

[Ollama für Windows](https://docs.ollama.com/windows) separat installieren.
Die offizielle Anwendung stellt ihre CLI und standardmäßig die API auf Port
11434 bereit. WSL und Bash sind für Text/Core nicht nötig.

## 2. Repository und Dependencies

```powershell
git clone https://github.com/YoungJibbit95/YJarvis.git
Set-Location YJarvis
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps/agent/requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
npm ci
```

Jeden Befehl und Exit-Status prüfen. Der direkte Python-Pfad braucht keine
venv-Aktivierung und keine Änderung der PowerShell Execution Policy.
Wenn PowerShell `npm.ps1` blockiert, `npm.cmd` für dieselben npm-Befehle verwenden.
`ELECTRON_SKIP_BINARY_DOWNLOAD` darf für einen tatsächlichen Desktop-Start nicht gesetzt sein.

## 3. Textmodell laden und starten

```powershell
ollama pull qwen2.5:3b-instruct
npm run dev
```

Ein antwortender Ollama-Server wird wiederverwendet. Falls noch keiner läuft,
startet der gemeinsame Launcher `ollama serve`, wartet auf Bereitschaft und
startet dann Backend, Vite und Electron. Optional kann `npm run dev:ollama`
in einem eigenen Terminal laufen. In der Anwendung zunächst Text verwenden;
Sprachmodus und automatische Sprachantworten ausschalten.

## 4. Start prüfen

```powershell
Invoke-RestMethod http://127.0.0.1:8787/health
Invoke-RestMethod http://127.0.0.1:8787/v1/setup/status
```

`/health` bestätigt das Backend. Setup prüft Modell-Inventar/Dateien, keine
erfolgreiche Generierung. Eine Textnachricht muss deshalb zusätzlich manuell
eine Antwort erzeugen. SQLite initialisiert beim Start im lokalen Runtime-Verzeichnis.

Python-Auswahl: `JARVIS_PYTHON_BIN` → `.venv\Scripts\python.exe` → `python`.
Der Override muss ein **einzelner Executable-Pfad** sein, kein String `py -3.11`:

```powershell
$env:JARVIS_PYTHON_BIN = (Resolve-Path .venv/Scripts/python.exe).Path
```

## 5. Beenden

Electron schließen oder im Launcher Ctrl-C verwenden. Der Launcher beendet
eigene Prozesse; ein unabhängig gestarteter Ollama-Server bleibt bestehen.
`JARVIS_BACKEND_MANAGED=external` bedeutet, dass der Backend-Prozess extern
verwaltet wird. Keine persönlichen Daten zur Fehlerbehebung löschen.

Originalanleitung und Startgrenzen:
[development.md]({{SOURCE}}/docs/development.md),
[Windows Text/Core]({{SOURCE}}/docs/architecture/windows-core-startup.md).
