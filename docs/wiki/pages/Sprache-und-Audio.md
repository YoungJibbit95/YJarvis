# Sprache und Audio

## Aktueller Legacy-Ablauf

```text
Mikrofon / MediaRecorder → Segment nach Sprechpause → Upload
→ Audio-Normalisierung → whisper.cpp-Prozess → Transkript
→ Legacy-Routing / Freigabe / Ollama → Antwort-Streaming
→ TTS-Synthese / Warteschlange → Wiedergabe
```

Sprachmodus per Klick starten/stoppen. Der vorhandene Sprachfilter erwartet
einen Präfix wie „Jarvis …“; nur „Jarvis“ wird ignoriert. Das ist keine
eigenständige ständig laufende Wake-Word-Engine. `Text only` deaktiviert
automatische gesprochene Antworten. Echo-Unterdrückung soll verhindern, dass
Lautsprecherausgabe erneut als Anfrage aufgenommen wird.

## STT

whisper.cpp benötigt ein kompatibles Binary und eine GGML-Modelldatei.
`whisper_binary` und `whisper_model_path` in Settings prüfen; ohne konfigurierten
Modellpfad greift der Default aus `WHISPER_MODEL`/Runtime. ffmpeg wird für
Normalisierung benötigt. Das Vorhandensein eines Modells beweist keine
funktionierende CLI oder gemessene Latenz.

## TTS und Wiedergabe

Piper nutzt ein ONNX-Modell mit zugehöriger JSON-Konfiguration; der Modellpfad
muss zur installierten Stimme passen. macOS `say` bleibt ein alternativer
Legacy-Backendpfad. Stimmenauflistung und Teile der Wiedergabe enthalten macOS-
Annahmen (`say`, `afplay`); daraus folgt keine Windows-Audiounterstützung.
Eine andere Sprachdatei alleine garantiert keine vollständige englische UI/NLU.

## Temporäre Daten

Upload-, STT- und TTS-Dateien werden nach Verarbeitung bereinigt. Zusätzlich
begrenzt die Wartung Anzahl und Alter in `runtime/audio` und `runtime/tts`.
Parameter siehe [Setup]({{WIKI}}/Setup). Diese Bereinigung ist kein Löschkonzept
für die dauerhaft gespeicherten Nachrichten oder Erinnerungen.

## Zukünftige Verbesserungen

YJ2-09 sieht eine explizite Voice-Zustandsmaschine und Latenzmessung vor.
YJ2-10 plant einen warmen/persistenten STT-Backendpfad mit Fallback und Restart.
Das Cross-Platform-Addendum fordert separate STT-/TTS-/Playback-Grenzen und
ehrliche Windows-Tests. Subsekundenwerte im Architekturplan sind Messziele,
keine heute erreichten Performance-Angaben.

Quelle: [audio.py]({{SOURCE}}/apps/agent/jarvis_agent/audio.py),
[README-Sprachmodus]({{SOURCE}}/README.md), [Roadmap]({{WIKI}}/Roadmap).
