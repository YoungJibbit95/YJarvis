# Sprache und Audio

## Aktueller Legacy-Ablauf

```text
Mikrofon / MediaRecorder → Segment nach Sprechpause → Upload
→ Audio-Normalisierung → whisper.cpp-Prozess → Transkript
→ Legacy-Routing / Freigabe / Ollama → Antwort-Streaming
→ TTS-Synthese / Warteschlange → Wiedergabe
```

Sprachmodus per Klick starten/stoppen. Ein Befehl kann direkt „Jarvis, öffne …“
enthalten oder als „Jarvis“ und Folgebefehl in zwei Aufnahmesegmenten erfolgen.
Nach dem alleinstehenden Wakeword gilt ein 8-Sekunden-Fenster, gemessen an der
Aufnahmezeit (nicht an der Whisper-Fertigstellung). Das ist keine neue akustische
Wakeword-Engine. Echo-Unterdrückung bleibt aktiv. `Text only` deaktiviert
automatisch gesprochene Antworten. Beim manuellen Stop werden gültige laufende
Aufnahmen final transkribiert und bleiben als angenommenes oder ausstehendes
Transkript sichtbar; ein expliziter Unmount-Abbruch verwirft weitere Verarbeitung.

## STT

whisper.cpp benötigt ein kompatibles Binary und eine GGML-Modelldatei.
`whisper_binary` und `whisper_model_path` in Settings prüfen; ohne konfigurierten
Modellpfad greift der Default aus `WHISPER_MODEL`/Runtime. ffmpeg wird für
WebM- und MP4-Normalisierung benötigt; Setup meldet fehlendes ffmpeg,
Whisper-Binary und Modelldateien getrennt. Die CLI hat großzügige endliche
Prozesslimits: ffmpeg 120 Sekunden, Whisper 480 Sekunden. Bei Ablauf werden
Kindprozesse beendet und temporäre Dateien bereinigt. Live-Zwischen-Whisper-
Aufrufe sind im Reliability-Fix deaktiviert: Die finale Transkription hat Vorrang.
Das Vorhandensein eines Modells beweist keine funktionierende CLI oder gemessene Latenz.

## Voice-Queue und Chat

Sprachbefehle erhalten lokale Äußerungs-IDs. Nur ein bestätigter `/v1/chat`-
Submit erzeugt einen Chat-Eintrag. Bei Netzwerkfehlern bleibt ein Befehl sichtbar
als *Ausgang unklar*; kein automatischer Retry löst womöglich dieselbe Aktion
erneut aus. Bei einer expliziten Wiederholung nach unbekanntem HTTP-Ausgang
wird das Risiko einer möglichen Doppelaktion bestätigt. Setup-Rechecks löschen
ausstehende Einträge nicht. Die bestehende Approval-/Policy-Pipeline bleibt
unverändert. Eine echte Exactly-once-Garantie würde einen gesondert genehmigten
serverseitigen Idempotenz-Vertrag erfordern.

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
