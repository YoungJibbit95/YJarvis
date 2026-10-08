# Dependencies

## Laufzeiten und Plattformen

| Komponente | Projektvorgabe | Zweck |
|---|---|---|
| Python | **3.11.x**, `.python-version` | Agent, Datenhaltung, Audio, Tests |
| Node.js | **22.x**, `.nvmrc` | Entwicklungslauncher, Vite, Electron |
| npm | passend zur Node-Installation | Workspaces und Installation des Lockfiles |
| Git | lokal verfügbar | Repository, Versionshistorie und Wiki-Pflege |
| Ollama | separat installiert | lokale Textgenerierung; nicht für modellfreie CI nötig |
| Windows | Windows 11 x64 als Projektziel | Text/Core; native Parität siehe Plattformstatus |
| macOS | Apple Silicon als Projektziel | bestehende native Legacy-Integrationen |
| Linux | Ubuntu 24.04 in CI | Headless-Checks, kein bestätigtes Desktop-Release |

Quellen: [.python-version]({{SOURCE}}/.python-version), [.nvmrc]({{SOURCE}}/.nvmrc),
[CI]({{SOURCE}}/.github/workflows/ci.yml). Upstream-Versionen ändern die
Projektvorgabe nicht automatisch. Node 24/26 oder die neueste Python-Version sind
kein Ersatz für die dokumentierte Testbasis.

## Python-Pakete

Direkte Runtime-Pins aus [requirements.txt]({{SOURCE}}/apps/agent/requirements.txt):

| Paket | Pin | Verantwortung |
|---|---|---|
| fastapi | 0.115.0 | HTTP-API |
| uvicorn[standard] | 0.31.0 | ASGI-Server |
| pydantic | 2.9.2 | API- und Domain-Datenvalidierung |
| aiosqlite | 0.20.0 | asynchroner SQLite-Zugriff |
| httpx | 0.27.2 | HTTP, unter anderem Ollama |
| python-multipart | 0.0.12 | Audio-Uploads |
| sounddevice | 0.5.1 | bestehende Audioabhängigkeit |
| soundfile | 0.12.1 | Audiodateien |
| piper-tts | 1.4.2 | lokale Sprachsynthese |

Entwicklerpakete: `pytest==8.3.5`, `ruff==0.11.13`, auf Windows
`tzdata==2026.5` für einen DST-Vertragstest. Python-Transitivabhängigkeiten sind
nicht vollständig gelockt; `pip check` prüft die aufgelöste Umgebung. Die
Runtime-Pins stehen zusätzlich in `apps/agent/pyproject.toml` und müssen synchron bleiben.

## JavaScript-Pakete

Die exakte aufgelöste Abhängigkeitsstruktur steht im
[package-lock.json]({{SOURCE}}/package-lock.json); mit `npm ci` installieren.
Die Desktop-Manifeste erlauben unter anderem React/React DOM `^18.3.1`, Electron
`^33.2.1`, TypeScript `^5.6.2`, Vite `^5.4.8` und das React-Plugin `^4.3.1`.
`@jarvis/shared-types` ist ein lokales Workspace-Paket. Manifestbereiche sind
keine Behauptung, dass genau deren Untergrenze installiert ist.

## Optionale native Komponenten und Modelle

| Komponente | Benötigt für | Grenze |
|---|---|---|
| ffmpeg | Audio-Normalisierung im STT-Pfad | ausführbares Programm, zusätzlich zu pip-Paketen |
| whisper.cpp + GGML-Modell | lokale Transkription | Binary und Modell sind getrennte Downloads |
| Piper `.onnx` + `.onnx.json` | neuronale Sprachausgabe | passendes Dateipaar und absolute Modellkonfiguration |
| macOS `say`, `afplay` | Systemstimme/Legacy-Wiedergabe | macOS-spezifisch |
| PortAudio/libsndfile | native Audiobibliotheken | Homebrew auf macOS, Systempakete in Linux-CI |
| Raycast | Launcher-Deeplinks | optional, macOS-spezifisch |

Es gibt keine gemessene allgemeine Mindest-RAM-/VRAM-Zusage. Der Hardware-Bereich
zeigt Basiswerte sowie separat native Windows-Grafikadapter; er ist kein
Benchmark und keine Modellberatung. Adapterinformationen beweisen keine
verfügbare Inferenzbeschleunigung.
Der kuratierte Katalog nennt für das Chatmodell etwa 1,9 GB Download und für
Whisper Small etwa 488 MB; das ist weder RAM-Bedarf noch gesamte Installationsgröße.

Upstream-Installationsquellen, geprüft am 2026-10-08:
[Python Windows](https://docs.python.org/3/using/windows.html),
[Node](https://nodejs.org/en/download), [Ollama Windows](https://docs.ollama.com/windows),
[whisper.cpp](https://github.com/ggml-org/whisper.cpp),
[Piper](https://github.com/OHF-Voice/piper1-gpl),
[Homebrew whisper.cpp](https://formulae.brew.sh/formula/whisper.cpp).
Die Homebrew-Formel heißt inzwischen `whisper.cpp` (früher `whisper-cpp`).
