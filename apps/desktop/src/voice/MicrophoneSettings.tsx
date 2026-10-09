import { useCallback, useEffect, useRef, useState } from "react";
import { transcribe } from "../api";
import { audioRms, microphoneConstraints, microphoneDeviceOptions, microphoneErrorMessage } from "./microphoneDevices";

type DiagnosticMode = "hardware" | "whisper";
type Phase = "idle" | "starting" | "recording" | "finalizing" | "complete" | "error";
type ActiveTest = {
  stream: MediaStream;
  context: AudioContext;
  recorder: MediaRecorder;
  timer: number | null;
  chunks: Blob[];
  mode: DiagnosticMode;
  generation: number;
  signal: boolean;
  aborted: boolean;
  started: number;
};

export function MicrophoneSettings({
  selectedId, onSelect, voiceActive, onDeviceUnavailable, sttAvailable
}: {
  selectedId: string;
  onSelect: (id: string) => void;
  voiceActive: boolean;
  onDeviceUnavailable: () => void;
  sttAvailable: boolean;
}) {
  const [devices, setDevices] = useState<Array<{ id: string; label: string }>>([]);
  const [deviceState, setDeviceState] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [permission, setPermission] = useState("Nicht geprüft");
  const [error, setError] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [mode, setMode] = useState<DiagnosticMode>("hardware");
  const [level, setLevel] = useState(0);
  const [signalSeen, setSignalSeen] = useState(false);
  const [result, setResult] = useState("");
  const [format, setFormat] = useState("");
  const [transcript, setTranscript] = useState("");
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [refresh, setRefresh] = useState(0);
  const alive = useRef(true);
  const generation = useRef(0);
  const active = useRef<ActiveTest | null>(null);
  const selectedRef = useRef(selectedId);
  selectedRef.current = selectedId;
  const onUnavailableRef = useRef(onDeviceUnavailable);
  onUnavailableRef.current = onDeviceUnavailable;
  const running = phase === "starting" || phase === "recording" || phase === "finalizing";

  const release = useCallback((test: ActiveTest) => {
    if (test.timer !== null) window.clearInterval(test.timer);
    test.stream.getTracks().forEach(track => track.stop());
    void test.context.close().catch(() => {});
    if (active.current === test) active.current = null;
  }, []);

  const abortTest = useCallback(() => {
    generation.current += 1;
    const current = active.current;
    if (current) {
      current.aborted = true;
      try { if (current.recorder.state !== "inactive") current.recorder.stop(); } catch { /* closed */ }
      release(current);
    }
    if (alive.current) { setLevel(0); setPhase("idle"); setResult("Test beendet, keine Audiodaten gespeichert."); }
  }, [release]);

  useEffect(() => () => {
    alive.current = false;
    generation.current += 1;
    const current = active.current;
    if (current) {
      current.aborted = true;
      try { if (current.recorder.state !== "inactive") current.recorder.stop(); } catch { /* closed */ }
      release(current);
    }
  }, [release]);

  useEffect(() => {
    let mounted = true;
    const media = navigator.mediaDevices;
    if (!media?.enumerateDevices) {
      setDeviceState("error"); setError("MediaDevices ist in dieser Umgebung nicht verfügbar.");
      return;
    }
    const inspect = async () => {
      try {
        const found = microphoneDeviceOptions(await media.enumerateDevices());
        if (!mounted) return;
        setDevices(found);
        setDeviceState(found.length ? "ready" : "empty");
        setError("");
        if (selectedRef.current && !found.some(item => item.id === selectedRef.current)) {
          setError("Das gespeicherte Mikrofon ist nicht angeschlossen. Bitte ausdrücklich ein neues Gerät wählen; kein automatischer Wechsel.");
          const test = active.current;
          if (test) {
            test.aborted = true;
            try { if (test.recorder.state !== "inactive") test.recorder.stop(); } catch { /* device gone */ }
            release(test);
            setPhase("error");
          }
          onUnavailableRef.current();
        }
      } catch (reason) {
        if (mounted) {
          setDeviceState("error");
          setError(microphoneErrorMessage(reason, window.jarvisDesktop?.platform || ""));
        }
      }
    };
    const handleChange = () => { void inspect(); };
    void inspect();
    media.addEventListener?.("devicechange", handleChange);
    void window.jarvisDesktop?.microphoneStatus?.().then(status => {
      if (mounted) setPermission(status === "granted"
        ? "OS-Status: erlaubt (Audiozugriff noch nicht getestet)"
        : status === "denied" || status === "restricted"
          ? "OS-Status: verweigert – Datenschutzeinstellungen prüfen"
          : status === "not-determined" ? "OS-Berechtigung noch nicht angefragt" : "OS-Berechtigungsstatus nicht zuverlässig verfügbar");
    }).catch(() => { if (mounted) setPermission("OS-Berechtigungsstatus nicht verfügbar"); });
    return () => { mounted = false; media.removeEventListener?.("devicechange", handleChange); };
  }, [refresh]);

  async function startTest(chosen: DiagnosticMode) {
    if (running || active.current || voiceActive) return;
    if (chosen === "whisper" && !sttAvailable) {
      setError("Whisper ist nicht bereit. Binary, Modell und FFmpeg im Setup prüfen. Mikrofon-Hardwaretest bleibt unabhängig verfügbar.");
      setPhase("error");
      return;
    }
    const current = ++generation.current;
    let stream: MediaStream | null = null;
    let context: AudioContext | null = null;
    try {
      setMode(chosen); setPhase("starting"); setError(""); setResult(""); setLevel(0);
      setSignalSeen(false); setTranscript(""); setLatencyMs(null); setFormat("");
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("MediaDevices/getUserMedia nicht verfügbar.");
      stream = await navigator.mediaDevices.getUserMedia(microphoneConstraints(selectedId));
      if (!alive.current || current !== generation.current) return;
      const tracks = stream.getAudioTracks();
      if (tracks.length !== 1 || tracks[0].readyState !== "live" || !tracks[0].enabled) {
        throw new Error("Kein aktiver Audio-Track. Mikrofon oder OS-Freigabe prüfen.");
      }
      const BrowserContext = window.AudioContext ||
        (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!BrowserContext) throw new Error("AudioContext ist nicht verfügbar.");
      context = new BrowserContext();
      const source = context.createMediaStreamSource(stream);
      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);
      await context.resume();
      if (!alive.current || current !== generation.current) return;
      if (typeof MediaRecorder === "undefined") throw new Error("MediaRecorder ist nicht verfügbar.");
      const recorder = new MediaRecorder(stream);
      const data = new Uint8Array(analyser.fftSize);
      const test: ActiveTest = {
        stream, context, recorder, chunks: [], timer: null, mode: chosen,
        generation: current, signal: false, aborted: false, started: Date.now()
      };
      active.current = test;
      recorder.ondataavailable = e => { if (!test.aborted && e.data.size) test.chunks.push(e.data); };
      recorder.onerror = () => {
        if (!test.aborted && alive.current && test.generation === generation.current) {
          test.aborted = true;
          try { if (recorder.state !== "inactive") recorder.stop(); } catch { /* broken recorder */ }
          release(test);
          setError("MediaRecorder meldet einen Aufnahmefehler.");
          setPhase("error");
        }
      };
      recorder.onstop = () => {
        release(test);
        if (test.aborted || !alive.current || test.generation !== generation.current) return;
        const blob = new Blob(test.chunks, { type: recorder.mimeType || "audio/webm" });
        setLevel(0);
        setFormat(blob.type + " · " + blob.size + " Bytes");
        if (!blob.size) {
          setError("MediaRecorder hat keine verwertbaren Audio-Daten erzeugt.");
          setPhase("error"); return;
        }
        if (!test.signal) {
          setError("Aufnahme vorhanden, aber kein relevantes Mikrofon-Signal gemessen. Pegel und Eingabegerät prüfen.");
          setPhase("error"); return;
        }
        if (test.mode === "hardware") {
          setResult("MediaStream, aktiver Track, Audio-Pegel und nicht-leerer MediaRecorder-Blob bestätigt. Keine Audiodaten hochgeladen.");
          setPhase("complete"); return;
        }
        setResult("Aufnahme erfolgreich · lokale Whisper-Transkription läuft …");
        setPhase("finalizing");
        void transcribe(blob).then(response => {
          if (!alive.current || test.generation !== generation.current) return;
          setTranscript(response.text || "(kein Text erkannt)");
          setLatencyMs(response.latency_ms);
          setResult("Whisper hat die lokale Testaufnahme verarbeitet. Kein Chat-Kommando gesendet.");
          setPhase("complete");
        }).catch(reason => {
          if (!alive.current || test.generation !== generation.current) return;
          setError("Whisper-Test fehlgeschlagen: " + (reason as Error).message);
          setPhase("error");
        });
      };
      // Audio samples, not decorative animation. No connection to speakers.
      test.timer = window.setInterval(() => {
        if (test.aborted || !alive.current) return;
        analyser.getByteTimeDomainData(data);
        const rms = audioRms(data);
        if (rms >= 0.012) { test.signal = true; setSignalSeen(true); }
        setLevel(Math.min(100, Math.round(rms * 300)));
      }, 80);
      recorder.start(250);
      setPermission("MediaStream geöffnet – tatsächlicher Audio-Track aktiv");
      setPhase("recording");
      setRefresh(n => n + 1);
      stream = null; context = null; // now owned by ActiveTest
    } catch (reason) {
      const test = active.current;
      if (test?.generation === current) {
        test.aborted = true;
        release(test);
      }
      if (alive.current && current === generation.current) {
        setError(microphoneErrorMessage(reason, window.jarvisDesktop?.platform || ""));
        setPhase("error");
      }
    } finally {
      if (stream) stream.getTracks().forEach(t => t.stop());
      if (context) void context.close().catch(() => {});
    }
  }

  function stopTest() {
    const test = active.current;
    if (!test || test.recorder.state !== "recording") return;
    setPhase("finalizing");
    test.recorder.stop(); // ondataavailable/onstop will finalize the real blob
  }

  return <div className="microphone-settings">
    <div className="settings-inline-heading">
      <strong>Mikrofon &amp; Berechtigungen</strong>
      <button type="button" className="secondary" onClick={() => setRefresh(n => n + 1)}>Geräte aktualisieren</button>
    </div>
    <label htmlFor="yj-microphone">Audio-Eingang</label>
    <select id="yj-microphone" value={selectedId} disabled={running} onChange={event => onSelect(event.target.value)}>
      <option value="">Systemstandard (bewusst auswählen)</option>
      {selectedId && !devices.some(item => item.id === selectedId)
        ? <option value={selectedId}>Ausgewähltes Gerät fehlt · erneut verbinden</option> : null}
      {devices.map(device => <option key={device.id} value={device.id}>{device.label}</option>)}
    </select>
    <p role="status" className="settings-hint">
      {deviceState === "loading" ? "Mikrofone werden erkannt …" :
        deviceState === "empty" ? "Keine benannten Audio-Eingänge erkannt; Systemstandard kann je nach OS verfügbar sein." :
        deviceState === "error" ? "Geräteinventur fehlgeschlagen." : devices.length + " Eingänge gemeldet."}
      {" · "}{permission}
    </p>
    <p className="settings-hint">Die Auswahl wird lokal gespeichert. Geräte-IDs können sich ändern. Ohne Zustimmung startet keine Aufnahme. Das Testsignal kommt ausschließlich aus echten Mikrofon-Samples.</p>
    <div className="mic-test-actions">
      {phase === "recording" ? <button type="button" onClick={stopTest}>Test beenden &amp; Aufnahme prüfen</button> : <>
        <button type="button" disabled={running || voiceActive} onClick={() => void startTest("hardware")}>Mikrofon testen</button>
        <button type="button" className="secondary" disabled={running || voiceActive} onClick={() => void startTest("whisper")}>Spracherkennung testen</button>
      </>}
      {running && <button type="button" className="secondary" onClick={abortTest}>Abbrechen</button>}
    </div>
    {voiceActive ? <p role="status">Sprachmodus läuft. Zum Testen bitte zuerst den Sprachmodus stoppen.</p> : null}
    <div className="mic-meter" role="meter" aria-label="Echter Mikrofonpegel" aria-valuemin={0} aria-valuemax={100} aria-valuenow={level}>
      <div className="mic-meter-fill" style={{ width: level + "%" }} />
    </div>
    <p className="settings-hint" role="status">
      {phase === "recording" ? (signalSeen ? "Aufnahme aktiv · Signal erkannt" : "Aufnahme aktiv · bisher kein deutliches Signal") :
        phase === "starting" ? "Fordere Mikrofonzugriff an …" :
        phase === "finalizing" ? "Aufnahme/Whisper wird verarbeitet …" :
        phase === "complete" ? "Test abgeschlossen" : phase === "error" ? "Test fehlgeschlagen" : "Mikrofon nicht aktiv"}
      {mode === "whisper" && phase !== "idle" ? " · Whisper-Test ohne Chat" : ""}
    </p>
    {format ? <p role="status">Testformat: {format}</p> : null}
    {result ? <p role="status">{result}</p> : null}
    {transcript ? <p role="status">Transkript: {transcript}</p> : null}
    {latencyMs !== null ? <p role="status">Whisper-Latenz: {latencyMs} ms</p> : null}
    {error ? <p role="alert" className="installation-error">{error}</p> : null}
  </div>;
}
