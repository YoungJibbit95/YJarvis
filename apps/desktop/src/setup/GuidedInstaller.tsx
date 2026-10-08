import { useEffect, useRef, useState } from "react";
import { fetchInstallOptions, setupInstallation, speak } from "../api";
import type { InstallOptions, InstallSelection, InstallState, InstallField } from "./installTypes";

const INITIAL: InstallState = { status: "idle", id: null, stage: "", completed: 0, total: null, error: null };
const FALLBACK: InstallOptions = { whisper_models: ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"], voices: [{ id: "de_DE-thorsten-medium", name: "Deutsch · Thorsten · medium" }] };
const size = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`;

export function GuidedInstaller({ onConfigured }: { onConfigured: (fields: InstallField[]) => void }) {
  const [selection, setSelection] = useState<InstallSelection>({ chat_model: "qwen2.5:3b-instruct", whisper_model: "small", voice: "de_DE-thorsten-medium", install_ollama: true });
  const [state, setState] = useState(INITIAL);
  const [options, setOptions] = useState(FALLBACK);
  const [error, setError] = useState<string | null>(null);
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [testingVoice, setTestingVoice] = useState(false);
  const notified = useRef<string | null>(null);
  const activeId = useRef<string | null>(null);
  const onConfiguredRef = useRef(onConfigured);
  onConfiguredRef.current = onConfigured;
  const busy = state.status === "running" || submitting;

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const deadline = window.setTimeout(() => controller.abort(), 20_000);
    setOptionsError(null);
    fetchInstallOptions(controller.signal).then(setOptions).catch(() => {
      if (active) setOptionsError("Vollständiger Stimmenkatalog nicht erreichbar. Thorsten bleibt auswählbar; erneut laden ist möglich.");
    }).finally(() => window.clearTimeout(deadline));
    return () => { active = false; controller.abort(); window.clearTimeout(deadline); };
  }, [attempt]);

  useEffect(() => {
    const controller = new AbortController();
    let timer: number;
    async function poll() {
      try {
        const next = await setupInstallation("status", undefined, controller.signal);
        if (controller.signal.aborted) return;
        setState(next);
        setError(null);
        if (next.status === "running") activeId.current = next.id;
        if (next.status === "completed" && next.id === activeId.current && next.id !== notified.current) {
          notified.current = next.id;
          onConfiguredRef.current(next.configured_fields ?? []);
        }
      } catch {
        if (!controller.signal.aborted) setError("Verbindung zur Einrichtung unterbrochen. Der Status wird erneut geprüft.");
      }
      if (!controller.signal.aborted) timer = window.setTimeout(() => void poll(), 1000);
    }
    void poll();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, []);

  async function start(chosen: InstallSelection) {
    setSubmitting(true); setError(null);
    try { const next = await setupInstallation("start", chosen); activeId.current = next.id; setState(next); }
    catch (reason) { setError((reason as Error).message); }
    finally { setSubmitting(false); }
  }
  async function cancel() {
    setSubmitting(true);
    try { setState(await setupInstallation("cancel")); }
    catch (reason) { setError((reason as Error).message); }
    finally { setSubmitting(false); }
  }

  return <section className="guided-installer" aria-labelledby="installation-title">
    <div className="section-heading"><p className="eyebrow">Einmal einrichten · direkt verwenden</p><h3 id="installation-title">Mach Jarvis startklar.</h3></div>
    <p>Wähle deine lokalen Modelle. Jarvis installiert fehlende Komponenten, prüft die Downloads und trägt die passenden Einstellungen ein.</p>
    <fieldset disabled={busy} className="installation-grid">
      <div className="installation-choice">
        <label htmlFor="install-chat">Chat-Modell · Ollama</label>
        <input id="install-chat" value={selection.chat_model ?? ""} placeholder="z. B. qwen2.5:3b-instruct" maxLength={160} onChange={e => setSelection({ ...selection, chat_model: e.target.value || null })} />
        <small>Jeder kompatible Ollama-Modellname. Größe und Hardwarebedarf hängen vom Modell ab.</small>
        <button type="button" disabled={!selection.chat_model} onClick={() => void start({ ...selection, whisper_model: null, voice: null })}>Chat-Modell installieren</button>
      </div>
      <div className="installation-choice">
        <label htmlFor="install-whisper">Spracheingabe · Whisper</label>
        <select id="install-whisper" value={selection.whisper_model ?? ""} onChange={e => setSelection({ ...selection, whisper_model: e.target.value || null })}>
          <option value="">Jetzt nicht installieren</option>{options.whisper_models.map(model => <option key={model} value={model}>{model}</option>)}
        </select>
        <small>Benötigte Windows-Programme wie whisper.cpp und FFmpeg werden mit eingerichtet.</small>
        <button type="button" disabled={!selection.whisper_model} onClick={() => void start({ chat_model: null, whisper_model: selection.whisper_model, voice: null, install_ollama: false })}>Spracheingabe installieren</button>
      </div>
      <div className="installation-choice">
        <label htmlFor="install-voice">Sprachausgabe · Piper</label>
        <select id="install-voice" value={selection.voice ?? ""} onChange={e => setSelection({ ...selection, voice: e.target.value || null })}>
          <option value="">Jetzt nicht installieren</option>{options.voices.map(voice => <option key={voice.id} value={voice.id}>{voice.name}</option>)}
        </select>
        <small>Modell und Konfiguration werden gemeinsam installiert. Nach dem Download hörst du eine kurze Hörprobe; Lizenzhinweise liegen bei der Stimme.</small>
        <button type="button" disabled={!selection.voice} onClick={() => void start({ chat_model: null, whisper_model: null, voice: selection.voice, install_ollama: false })}>Stimme installieren</button>
      </div>
    </fieldset>
    {optionsError && <p role="status">{optionsError} <button type="button" disabled={busy} onClick={() => setAttempt(x => x + 1)}>Katalog erneut laden</button></p>}
    <div className="installation-actions">
      <button type="button" disabled={busy || !selection.chat_model} onClick={() => void start(selection)}>Auswahl installieren &amp; vorkonfigurieren</button>
      <button type="button" className="secondary" disabled={busy} onClick={() => void start({ chat_model: null, whisper_model: null, voice: null, install_ollama: true })}>Nur Ollama einrichten</button>
      {state.status === "running" && <button type="button" className="secondary" disabled={submitting || state.cancellable === false} onClick={() => void cancel()}>Abbrechen</button>}
    </div>
    <p className="installation-note">Downloads können mehrere GB benötigen. Vorhandene Programme werden verwendet; nur die gewählten Modelleinstellungen werden angepasst. Auf macOS/Linux werden Systemprogramme über den Paketmanager eingerichtet.</p>
    {state.status !== "idle" && <div className="installation-progress" data-status={state.status} role="status" aria-live="polite">
      <strong>{state.stage}</strong>
      {state.status === "running" && <><progress max={state.total || undefined} value={state.total ? state.completed : undefined} aria-label="Downloadfortschritt" /><span>{state.total ? `${size(state.completed)} / ${size(state.total)}` : "Wird vorbereitet oder geprüft …"}</span></>}
      {state.error && <p role="alert">{state.error}</p>}
      {state.status === "completed" && <button type="button" disabled={testingVoice} onClick={async () => {
        setTestingVoice(true); setError(null);
        try { await speak("Hallo. Ich bin Jarvis. Deine Stimme ist eingerichtet."); }
        catch (reason) { setError((reason as Error).message); }
        finally { setTestingVoice(false); }
      }}>Stimme testen</button>}
    </div>}
    {error && <p className="installation-error" role="alert">{error}</p>}
  </section>;
}
