# Installation auf macOS

macOS Apple Silicon behält seine Legacy-Automation. Dieser Guide beschreibt
Quellcodebetrieb; Homebrew-, Mikrofon- und Automationstests wurden in diesem
Dokumentationszyklus auf Windows **nicht** ausgeführt.

## 1. Voraussetzungen

Mit vorhandenem Homebrew:

```bash
brew install python@3.11 node@22 ollama ffmpeg whisper.cpp portaudio libsndfile
export PATH="$(brew --prefix node@22)/bin:$PATH"
python3.11 --version
node --version
npm --version
```

Die aktuelle [Homebrew-Formel](https://formulae.brew.sh/formula/whisper.cpp) heißt
`whisper.cpp`; ältere Projekttexte verwenden noch `whisper-cpp`.
Weitere offizielle Formeln: [Python 3.11](https://formulae.brew.sh/formula/python@3.11),
[Node 22](https://formulae.brew.sh/formula/node@22),
[ffmpeg](https://formulae.brew.sh/formula/ffmpeg).
Die installierte Whisper-CLI muss mit dem vorhandenen Adapter kompatibel sein;
eine Formelinstallation beweist noch keine Transkription.

## 2. Projekt installieren

```bash
git clone https://github.com/YoungJibbit95/YJarvis.git
cd YJarvis
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r apps/agent/requirements.txt -r requirements-dev.txt
python -m pip check
npm ci
```

## 3. Modelle einrichten

```bash
ollama pull qwen2.5:3b-instruct
./scripts/download-whisper-model.sh ggml-small.bin
```

Der Download-Helfer ist ein vorhandenes Bash-Skript. Es ist keine native
Windows-Anleitung. Für Piper ein zusammengehöriges `.onnx`-/`.onnx.json`-Paar
in `runtime/models/` ablegen und den absoluten Modellpfad in Settings setzen.
Modell-Lizenzen gesondert prüfen; die Lizenz eines Sprachdatensatzes bestätigt
nicht automatisch die Lizenz der Gewichte. Alternativ bleibt `tts_engine=say`
auf macOS möglich.

## 4. Start und Rechte

```bash
npm run dev
```

Der Launcher nutzt oder startet Ollama, startet den Agenten und öffnet Electron.
Mikrofonzugriff und erforderliche macOS-Automation nur für die benötigten
Integrationen freigeben. Tool-Freigaben in YJarvis bleiben zusätzlich erforderlich.
`/health`, eine echte Textantwort und anschließend gezielt Audio/Tool-Funktionen
prüfen. Nicht allein aus einem erfolgreichen Build auf funktionierende Audio-
oder AppleScript-Integration schließen.

Optionaler Python-Override:

```bash
export JARVIS_PYTHON_BIN="$PWD/.venv/bin/python"
```

Quelle und manuelle Checkliste: [development.md]({{SOURCE}}/docs/development.md).
