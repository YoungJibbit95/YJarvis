import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import type { JarvisSettings } from "@jarvis/shared-types";
import { fetchModelInventory, speak } from "../api";
import type { ModelInventory } from "../setup/modelInventory";
import type { SetupCheck } from "../setup/types";
import type { InstallField } from "../setup/installTypes";
import { GuidedInstaller } from "../setup/GuidedInstaller";
import { ModelCatalogBrowser } from "../setup/ModelCatalogBrowser";
import { MicrophoneSettings } from "../voice/MicrophoneSettings";

type Section = "input" | "models" | "output" | "advanced";
const SECTIONS: Array<{ id: Section; title: string }> = [
  { id: "input", title: "Spracheingabe" },
  { id: "models", title: "KI & Modelle" },
  { id: "output", title: "Sprachausgabe" },
  { id: "advanced", title: "System & Erweitert" },
];

type Props = {
  settings: JarvisSettings;
  draft: JarvisSettings;
  setDraft: Dispatch<SetStateAction<JarvisSettings>>;
  setupCheck: SetupCheck;
  sayVoices: string[];
  onRefreshVoices: () => Promise<void>;
  onSave: () => Promise<void>;
  onConfigured: (fields: InstallField[]) => void;
  selectedMicId: string;
  onSelectMic: (id: string) => void;
  voiceActive: boolean;
  voiceStage?: string;
  onStartVoiceTest?: () => void;
  onMicUnavailable: () => void;
  allowlistInput: string;
  onAllowlistInput: (value: string) => void;
  onAddPath: () => void;
  onRemovePath: (path: string) => void;
};

export function IntelligentSettings({
  settings, draft, setDraft, setupCheck, sayVoices, onRefreshVoices, onSave, onConfigured,
  selectedMicId, onSelectMic, voiceActive, voiceStage, onStartVoiceTest, onMicUnavailable, allowlistInput,
  onAllowlistInput, onAddPath, onRemovePath
}: Props) {
  const [section, setSection] = useState<Section>("input");
  const [inventory, setInventory] = useState<ModelInventory | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [reload, setReload] = useState(0);
  const [search, setSearch] = useState("");
  const [installerOpen, setInstallerOpen] = useState(false);
  const [preview, setPreview] = useState<"idle" | "playing" | "done" | "error">("idle");
  const [previewError, setPreviewError] = useState("");
  const dirty = useMemo(() => JSON.stringify(settings) !== JSON.stringify(draft), [settings, draft]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setLoadError("");
    void fetchModelInventory(controller.signal).then(data => {
      if (!controller.signal.aborted) setInventory(data);
    }).catch(reason => {
      if (!controller.signal.aborted) setLoadError((reason as Error).message);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [reload]);

  const change = (fields: Partial<JarvisSettings>) => setDraft(previous => ({ ...previous, ...fields }));
  const installedChat = inventory?.ollama.models.filter(item =>
    item.name.toLowerCase().includes(search.toLowerCase().trim())) || [];
  const knownChat = inventory?.ollama.models.some(item => item.name === draft.model_name) ?? false;
  const whisper = inventory?.whisper.models || [];
  const whisperKnown = whisper.some(item => item.path === draft.whisper_model_path);
  const voices = inventory?.tts.piper_voices || [];
  const currentPiper = voices.some(item => item.path === draft.tts_model_path);
  const sayAvailable = inventory?.tts.say_supported === true;
  const usingSay = draft.tts_engine.toLowerCase() === "say";
  const readyToPreview = settings.tts_engine === draft.tts_engine &&
    settings.tts_voice === draft.tts_voice && settings.tts_model_path === draft.tts_model_path;
  async function testVoice() {
    setPreview("playing"); setPreviewError("");
    try {
      await speak("Hallo, ich bin Jarvis. So klingt die aktuell gespeicherte Stimme.");
      setPreview("done");
    } catch (reason) {
      setPreview("error"); setPreviewError((reason as Error).message);
    }
  }

  return <section className="panel settings">
    <header className="panel-header">
      <div><p className="eyebrow">Dein Jarvis · Geräte und Modelle</p><h2>Einstellungen</h2></div>
      <p>Wähle aus echten Geräte- und Modellinventaren. Änderungen werden erst durch Speichern aktiv.</p>
    </header>
    <nav className="settings-nav" aria-label="Einstellungsbereiche">
      {SECTIONS.map(item => <button key={item.id} type="button" className={section === item.id ? "settings-nav-active" : "secondary"}
        aria-current={section === item.id ? "page" : undefined}
        onClick={() => setSection(item.id)}>{item.title}</button>)}
    </nav>
    <div className="panel-scroll settings-scroll settings-experience">
      {section === "input" && <section className="settings-focus" aria-labelledby="settings-input-title">
        <div className="settings-inline-heading"><h3 id="settings-input-title">Spracheingabe</h3>
          <span className="settings-pill">{setupCheck.report?.stt.status === "available" ? "Whisper bereit laut Setup" : "Whisper nicht bestätigt"}</span>
        </div>
        <p>Prüfe zuerst das Mikrofon. Der Hardwaretest funktioniert auch dann, wenn Whisper noch nicht installiert ist.</p>
        <MicrophoneSettings selectedId={selectedMicId} onSelect={onSelectMic} voiceActive={voiceActive}
          onDeviceUnavailable={onMicUnavailable} sttAvailable={setupCheck.report?.stt.status === "available"}
          onStartVoiceTest={onStartVoiceTest} voiceStage={voiceStage} />
        <div className="settings-subsection">
          <div className="settings-inline-heading"><h4>Whisper-Modell</h4>
            <button type="button" className="secondary" onClick={() => setReload(n => n + 1)}>Modelle aktualisieren</button>
          </div>
          <p>Installierte Dateien aus dem YJarvis-Modellordner oder deinem ausdrücklich konfigurierten Pfad.</p>
          {loading ? <p role="status">Lade lokale Sprachmodelle …</p> :
            <label>Modell auswählen
              <select value={draft.whisper_model_path} onChange={event => change({ whisper_model_path: event.target.value })}>
                {!whisperKnown ? <option value={draft.whisper_model_path}>
                  {draft.whisper_model_path ? "Aktueller eigener Pfad (nicht bestätigt)" : "Kein Modell ausgewählt"}
                </option> : null}
                {whisper.map(item => <option key={item.path} value={item.path}>{item.name} · Datei vorhanden</option>)}
              </select>
            </label>}
          {inventory && <p role="status">Whisper CLI: {inventory.whisper.binary_available ? "gefunden" : "fehlt"} ·
            FFmpeg: {inventory.whisper.ffmpeg_available ? "gefunden" : "fehlt"}.
            Eine vorhandene Datei ist noch kein erfolgreicher Transkriptionstest.</p>}
        </div>
      </section>}

      {section === "models" && <section className="settings-focus" aria-labelledby="settings-models-title">
        <div className="settings-inline-heading"><h3 id="settings-models-title">KI &amp; Modelle</h3>
          <button type="button" className="secondary" onClick={() => setReload(n => n + 1)}>Ollama aktualisieren</button>
        </div>
        <p>Die Liste stammt von <code>/api/tags</code> deiner konfigurierten Ollama-Instanz.
          „Installiert“ garantiert keine erfolgreiche Inferenz.</p>
        {loading ? <p role="status">Ollama-Modellinventar wird geladen …</p> : null}
        {loadError ? <p role="alert">Inventurfehler: {loadError} <button type="button" onClick={() => setReload(n => n + 1)}>Erneut versuchen</button></p> : null}
        {inventory && <p role="status">Ollama: {inventory.ollama.status === "online" ? "verbunden" :
          inventory.ollama.status === "offline" ? "nicht erreichbar" : "Inventur fehlgeschlagen"}.
          {inventory.ollama.error ? " " + inventory.ollama.error : ""}
        </p>}
        <label className="settings-search">Installierte Modelle durchsuchen
          <input value={search} onChange={event => setSearch(event.target.value)} placeholder="Name oder Tag suchen" />
        </label>
        <label>Aktives Modell für den nächsten Speichervorgang
          <select value={draft.model_name} onChange={event => change({ model_name: event.target.value })}>
            {!knownChat ? <option value={draft.model_name}>
              {draft.model_name || "(keines)"} · nicht in aktueller Inventur bestätigt
            </option> : null}
            {installedChat.map(model => <option value={model.name} key={model.digest + model.name}>
              {model.name} · installiert{model.active ? " · aktiv" : ""}
              {model.size_bytes !== null ? " · " + (model.size_bytes / 1024 ** 3).toFixed(2) + " GB" : ""}
            </option>)}
            {knownChat && search && !installedChat.some(model => model.name === draft.model_name)
              ? <option value={draft.model_name}>{draft.model_name} · ausgewählt (außerhalb des Filters)</option> : null}
          </select>
        </label>
        {inventory?.ollama.status === "online" && inventory.ollama.models.length === 0
          ? <p role="status">Ollama meldet keine installierten Modelle. Guided Setup kann welche installieren.</p> : null}
      </section>}

      {section === "output" && <section className="settings-focus" aria-labelledby="settings-output-title">
        <h3 id="settings-output-title">Sprachausgabe</h3>
        <p>Es werden nur vorhandene Engine-Optionen und erkannte Stimmen angeboten. Eine Hörprobe verwendet die aktuell <strong>gespeicherte</strong> Stimme.</p>
        <div className="form-grid">
          <label>TTS-Engine
            <select value={draft.tts_engine} onChange={event => change({ tts_engine: event.target.value })}>
              <option value="piper">Piper · lokal</option>
              {sayAvailable ? <option value="say">macOS-Systemstimmen · say</option> : null}
              {!sayAvailable && usingSay ? <option value="say">say · hier nicht unterstützt (bestehende Auswahl)</option> : null}
              {!["piper", "say"].includes(draft.tts_engine) ? <option value={draft.tts_engine}>{draft.tts_engine} · benutzerdefiniert</option> : null}
            </select>
          </label>
          {usingSay ? <label>Systemstimme
            <select value={draft.tts_voice} onChange={event => change({ tts_voice: event.target.value })}>
              {draft.tts_voice && !sayVoices.includes(draft.tts_voice) ? <option value={draft.tts_voice}>{draft.tts_voice} · aktuell</option> : null}
              {sayVoices.map(voice => <option value={voice} key={voice}>{voice}</option>)}
            </select>
            {sayAvailable ? <button type="button" className="secondary" onClick={() => void onRefreshVoices()}>Stimmen neu laden</button>
              : <span role="status">say ist auf dieser Plattform nicht verfügbar.</span>}
          </label> : <label>Piper-Stimme
            <select value={draft.tts_model_path} onChange={event => {
              const item = voices.find(voice => voice.path === event.target.value);
              if (item) change({ tts_model_path: item.path, tts_voice: item.name });
            }}>
              {!currentPiper ? <option value={draft.tts_model_path}>{draft.tts_model_path ? "Bisheriger eigener Modellpfad (nicht bestätigt)" : "Keine Stimme ausgewählt"}</option> : null}
              {voices.map(voice => <option key={voice.path} value={voice.path}>{voice.name} · Modell &amp; Config vorhanden</option>)}
            </select>
          </label>}
        </div>
        {inventory && <p role="status">Piper-Runtime: {inventory.tts.piper_runtime_available ? "erkannt" : "nicht gefunden"} ·
          {" "}{voices.length} vollständige Stimmenpaare gefunden. Eine installierte Stimme garantiert keine Audioausgabe.</p>}
        <div className="mic-test-actions">
          <button type="button" disabled={!readyToPreview || preview === "playing"} onClick={() => void testVoice()}>
            {preview === "playing" ? "Hörprobe läuft …" : "Stimme anhören"}
          </button>
          {!readyToPreview ? <span>Für diese Auswahl zuerst speichern.</span> : null}
        </div>
        {preview === "done" ? <p role="status">Backend-Hörprobe abgeschlossen. Lautsprecherstatus ist nicht separat verifiziert.</p> : null}
        {previewError ? <p role="alert">{previewError}</p> : null}
      </section>}

      {section === "advanced" && <section className="settings-focus" aria-labelledby="settings-advanced-title">
        <h3 id="settings-advanced-title">System &amp; Erweitert</h3>
        <p>Individuelle Modell-Tags, Dateipfade, Sicherheit und Aussprache bleiben hier vollständig bearbeitbar.</p>
        <div className="form-grid">
          <label>Sprache <input value={draft.language} onChange={event => change({ language: event.target.value })} /></label>
          <label>Eigener Chat-Modell-Tag <input value={draft.model_name} onChange={event => change({ model_name: event.target.value })} /></label>
          <label>Ollama URL <input value={draft.ollama_base_url} onChange={event => change({ ollama_base_url: event.target.value })} /></label>
          <label>Whisper-Modellpfad <input value={draft.whisper_model_path} onChange={event => change({ whisper_model_path: event.target.value })} /></label>
          <label>Whisper Binary <input value={draft.whisper_binary} onChange={event => change({ whisper_binary: event.target.value })} /></label>
          <label>Piper-Modellpfad <input value={draft.tts_model_path} onChange={event => change({ tts_model_path: event.target.value })} /></label>
          <label>Stimmenname <input value={draft.tts_voice} onChange={event => change({ tts_voice: event.target.value })} /></label>
          <label>Sir-Aussprache <input value={draft.tts_sir_pronunciation} onChange={event => change({ tts_sir_pronunciation: event.target.value })} /></label>
          <label>say Sprechtempo (WPM) <input type="number" min={80} max={420} value={draft.say_rate_wpm}
            onChange={event => change({ say_rate_wpm: Number(event.target.value) || 235 })} /></label>
        </div>
        <div className="settings-subsection allowlist">
          <h4>Dateizugriff · explizite Allowlist</h4>
          <div className="allowlist-add"><input value={allowlistInput} aria-label="Erlaubten Pfad hinzufügen"
            onChange={event => onAllowlistInput(event.target.value)} placeholder="Vollständigen Ordnerpfad eingeben" />
            <button type="button" onClick={onAddPath}>Hinzufügen</button></div>
          <ul>{draft.allowed_paths.map(path => <li key={path}><code>{path}</code>
            <button type="button" className="secondary" onClick={() => onRemovePath(path)}>Entfernen</button></li>)}
            {!draft.allowed_paths.length ? <li>Keine Allowlist-Pfade gesetzt.</li> : null}
          </ul>
        </div>
      </section>}

      <div className="settings-installer-area">
        <button type="button" className="secondary" aria-expanded={installerOpen} onClick={() => setInstallerOpen(x => !x)}>
          {installerOpen ? "Einrichtung einklappen" : "Weitere Modelle & Stimmen installieren"}
        </button>
        {installerOpen && <>
          <GuidedInstaller onConfigured={fields => { onConfigured(fields); setReload(n => n + 1); }} />
          <ModelCatalogBrowser />
        </>}
      </div>
      <p className="settings-hint">Installationsfortschritt, Abbruch und Verifizierung stammen aus dem vorhandenen SetupInstaller. Es werden keine Modelle automatisch gewechselt.</p>
    </div>
    <div className="settings-footer">
      <button type="button" onClick={() => void onSave()} disabled={!dirty}>Änderungen speichern</button>
      <span role="status">{dirty ? "Nicht gespeicherte Änderungen" : "Einstellungen gespeichert"} · Aktiv: {settings.model_name}</span>
    </div>
  </section>;
}
