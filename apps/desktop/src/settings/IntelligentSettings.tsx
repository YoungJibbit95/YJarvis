import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import type { JarvisSettings } from "@jarvis/shared-types";
import { fetchModelCatalog, fetchInstallOptions, fetchModelInventory, speak } from "../api";
import type { ModelCatalogEntry } from "../setup/modelCatalog";
import type { InstallOptions, InstallSelection } from "../setup/installTypes";
import type { ModelInventory } from "../setup/modelInventory";
import type { SetupCheck } from "../setup/types";
import type { InstallField } from "../setup/installTypes";
import { GuidedInstaller } from "../setup/GuidedInstaller";
import { ModelCatalogBrowser } from "../setup/ModelCatalogBrowser";
import { MicrophoneSettings } from "../voice/MicrophoneSettings";

type Section = "overview" | "input" | "models" | "output" | "advanced";
type InstallTarget = { category: "chat" | "whisper" | "voice"; model: string | null };
const SECTIONS: Array<{ id: Section; title: string }> = [
  { id: "overview", title: "Übersicht" },
  { id: "input", title: "Spracheingabe" },
  { id: "models", title: "KI & Modelle" },
  { id: "output", title: "Sprachausgabe" },
  { id: "advanced", title: "System & Erweitert" },
];

function StatusCard({ title, status, detail, action, tone, onClick }: {
  title: string; status: string; detail: string; action: string;
  tone: "ready" | "warning" | "unknown"; onClick: () => void;
}) {
  return <article className="yj-settings-status-card" data-tone={tone}>
    <span className="yj-settings-card-eyebrow">{title}</span>
    <strong>{status}</strong>
    <p>{detail}</p>
    <button type="button" className="secondary" onClick={onClick}>{action} <span aria-hidden="true">→</span></button>
  </article>;
}

function gigabytes(bytes: number | null): string {
  return bytes === null ? "Größe unbekannt" : (bytes / 1024 ** 3).toFixed(2) + " GB";
}

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
  const [section, setSection] = useState<Section>("overview");
  const contentRef = useRef<HTMLDivElement | null>(null);
  const [inventory, setInventory] = useState<ModelInventory | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [reload, setReload] = useState(0);
  const [search, setSearch] = useState("");
  const [voiceSearch, setVoiceSearch] = useState("");
  const [installerOpen, setInstallerOpen] = useState(false);
  const [installTarget, setInstallTarget] = useState<InstallTarget | null>(null);
  const [installOptions, setInstallOptions] = useState<InstallOptions | null>(null);
  const [catalog, setCatalog] = useState<ModelCatalogEntry[]>([]);
  const [catalogError, setCatalogError] = useState("");
  const [inventoryStatus, setInventoryStatus] = useState<"checking" | "ready" | "error">("checking");
  const [micHardwareTested, setMicHardwareTested] = useState(false);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveError, setSaveError] = useState("");
  const [preview, setPreview] = useState<"idle" | "playing" | "done" | "error">("idle");
  const [previewError, setPreviewError] = useState("");
  const dirty = useMemo(() => JSON.stringify(settings) !== JSON.stringify(draft), [settings, draft]);

  useEffect(() => {
    // Keep opened install options and switched sections immediately visible in
    // the scrollable content area, without moving the surrounding app shell.
    contentRef.current?.scrollTo?.({ top: 0, behavior: "auto" });
  }, [section, installerOpen, installTarget?.category, installTarget?.model]);

  useEffect(() => {
    // A test on a former device is not evidence for a newly chosen microphone.
    setMicHardwareTested(false);
  }, [selectedMicId]);

  useEffect(() => {
    const controller = new AbortController();
    setCatalogError("");
    setInstallOptions(null);
    void Promise.allSettled([
      Promise.resolve().then(() => fetchInstallOptions(controller.signal)),
      Promise.resolve().then(() => fetchModelCatalog(controller.signal))
    ]).then(([installedOptions, knownModels]) => {
      if (controller.signal.aborted) return;
      if (installedOptions.status === "fulfilled") setInstallOptions(installedOptions.value);
      else setCatalogError("Installationskatalog nicht erreichbar. Erneut laden.");
      if (knownModels.status === "fulfilled") setCatalog(knownModels.value);
      else setCatalogError("Unterstützte Modellquellen nicht erreichbar. Erneut laden.");
    });
    return () => controller.abort();
  }, [reload]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setInventoryStatus("checking"); setLoadError("");
    void fetchModelInventory(controller.signal).then(data => {
      if (!controller.signal.aborted) { setInventory(data); setInventoryStatus("ready"); }
    }).catch(reason => {
      if (!controller.signal.aborted) { setLoadError((reason as Error).message); setInventoryStatus("error"); }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [reload]);

  const change = (fields: Partial<JarvisSettings>) => {
    setSaveState("idle");
    setDraft(previous => ({ ...previous, ...fields }));
  };
  function openInstaller(category: InstallTarget["category"] | null = null, model: string | null = null) {
    setInstallTarget(category ? { category, model } : null);
    setInstallerOpen(true);
  }
  const installSelection: Partial<InstallSelection> | undefined = !installTarget ? undefined : {
    chat_model: installTarget.category === "chat" ? installTarget.model : null,
    whisper_model: installTarget.category === "whisper" ? installTarget.model : null,
    voice: installTarget.category === "voice" ? installTarget.model : null,
    install_ollama: installTarget.category === "chat",
  };
  async function saveDraft() {
    if (!dirty || saveState === "saving") return;
    setSaveState("saving"); setSaveError("");
    try { await onSave(); setSaveState("saved"); }
    catch (reason) {
      setSaveState("error");
      setSaveError(reason instanceof Error ? reason.message : String(reason));
    }
  }
  function discardDraft() {
    setDraft(settings);
    setSaveState("idle"); setSaveError("");
    onAllowlistInput("");
  }
  const installedChat = inventory?.ollama.models.filter(item =>
    item.name.toLowerCase().includes(search.toLowerCase().trim())) || [];
  const knownChat = inventory?.ollama.models.some(item => item.name === draft.model_name) ?? false;
  const whisper = inventory?.whisper.models || [];
  const whisperKnown = whisper.some(item => item.path === draft.whisper_model_path);
  const voices = inventory?.tts.piper_voices || [];
  const currentPiper = voices.some(item => item.path === draft.tts_model_path);
  const sayAvailable = inventory?.tts.say_supported === true;
  const usingSay = draft.tts_engine.toLowerCase() === "say";
  const chatCatalog = catalog.filter(item => item.category === "chat" && !inventory?.ollama.models.some(
    installed => installed.name === item.runtime.model_id
  ));
  const moreVoices = installOptions?.voices.filter(item =>
    item.name.toLowerCase().includes(voiceSearch.toLowerCase().trim()) ||
    item.id.toLowerCase().includes(voiceSearch.toLowerCase().trim())
  ) || [];
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

  return <section className="panel settings yj-settings-panel">
    <header className="panel-header yj-settings-header">
      <div>
        <p className="eyebrow">Persönliche Kontrolle · lokale Geräte und Modelle</p>
        <h2>Einstellungen</h2>
      </div>
      <p>Jarvis erkennt, was installiert ist. Du entscheidest, welches Gerät oder Modell verwendet wird.</p>
    </header>
    <div className="yj-settings-workbench">
      <aside className="yj-settings-sidebar">
        <p className="eyebrow">Bereiche</p>
        <nav className="settings-nav" aria-label="Einstellungsbereiche">
          {SECTIONS.map(item => <button key={item.id} type="button"
            className={section === item.id ? "settings-nav-active" : "secondary"}
            aria-current={section === item.id ? "page" : undefined}
            onClick={() => setSection(item.id)}>
            <span>{item.title}</span><span aria-hidden="true">›</span>
          </button>)}
        </nav>
        <div className="yj-settings-sidebar-state" role="status">
          <strong>{dirty ? "Änderungen offen" : "Alles gespeichert"}</strong>
          <span>{loading ? "Inventur wird geladen" : inventory?.ollama.status === "online"
            ? "Ollama erreichbar" : "Modellverbindung ungeprüft"}</span>
          <button type="button" className="secondary" onClick={() => setReload(value => value + 1)}>
            Status aktualisieren
          </button>
        </div>
      </aside>
      <div ref={contentRef} className="panel-scroll settings-scroll settings-experience" aria-live="off">
        {installerOpen && <section className="yj-settings-install-drawer" aria-label="Komponenten installieren">
          <header className="settings-inline-heading">
            <div>
              <p className="eyebrow">Vorhandenen Installer verwenden</p>
              <h3>Komponente einrichten</h3>
              <p>Die Auswahl wird vorbefüllt. Erst dein Klick auf „Installieren“ startet einen Download.</p>
            </div>
            <button type="button" className="secondary" onClick={() => setInstallerOpen(false)}>Einrichtung schließen</button>
          </header>
          <GuidedInstaller initialSelection={installSelection}
            onConfigured={fields => { onConfigured(fields); setReload(n => n + 1); }} />
          <ModelCatalogBrowser />
        </section>}
        {section === "overview" && <section className="settings-focus yj-settings-overview" aria-labelledby="yj-settings-overview-title">
          <div className="yj-settings-hero">
            <p className="eyebrow">Setup-Zentrale</p>
            <h3 id="yj-settings-overview-title">So ist dein Jarvis eingerichtet.</h3>
            <p>Die Statusanzeigen basieren auf der aktuellen Runtime. „Vorhanden“ bedeutet nicht, dass Mikrofon, Inferenz oder Lautsprecher bereits erfolgreich getestet wurden.</p>
            <div className="mic-test-actions">
              <button type="button" onClick={() => setSection("input")}>Mikrofon einrichten</button>
              <button type="button" className="secondary" onClick={() => setSection("models")}>KI-Modell auswählen</button>
              <button type="button" className="secondary" onClick={() => openInstaller()}>Komponenten installieren</button>
            </div>
          </div>
          <div className="yj-settings-dashboard-cards">
            <StatusCard title="Mikrofon" tone={micHardwareTested ? "ready" : "unknown"}
              status={micHardwareTested ? "Hardwaretest erfolgreich" : "Hardware noch nicht getestet"}
              detail={selectedMicId ? "Ein bestimmtes Mikrofon ist gewählt." : "Systemstandard eingestellt."}
              action="Mikrofon & Diagnose" onClick={() => setSection("input")} />
            <StatusCard title="Chat-Modell" tone={inventory?.ollama.status === "online" ? "ready" : "warning"}
              status={loading ? "Wird geprüft" : inventory?.ollama.status === "online"
                ? "Ollama erreichbar" : "Verbindung nicht bestätigt"}
              detail={settings.model_name + " · " + (inventory?.ollama.models.length ?? 0) + " gemeldete Modelle. Inferenz nicht geprüft."}
              action="Modelle ansehen" onClick={() => setSection("models")} />
            <StatusCard title="Spracherkennung" tone={setupCheck.report?.stt.status === "available" ? "ready" : "warning"}
              status={setupCheck.report?.stt.status === "available" ? "STT laut Setup verfügbar" : "Einrichtung prüfen"}
              detail={inventory ? "Whisper CLI: " + (inventory.whisper.binary_available ? "gefunden" : "fehlt") +
                " · FFmpeg: " + (inventory.whisper.ffmpeg_available ? "gefunden" : "fehlt") :
                "Komponenten werden eingelesen."}
              action="Whisper einrichten" onClick={() => setSection("input")} />
            <StatusCard title="Sprachausgabe" tone={inventory?.tts.piper_voices.length ? "ready" : "unknown"}
              status={loading ? "Wird geprüft" : (inventory?.tts.piper_voices.length ?? 0) + " Piper-Stimmenpaare"}
              detail={"Aktive Engine: " + settings.tts_engine + ". Lautsprecherausgabe noch nicht bestätigt."}
              action="Stimmen auswählen" onClick={() => setSection("output")} />
          </div>
          <div className="settings-subsection yj-settings-next">
            <div className="settings-inline-heading">
              <div><h4>Deine Konfiguration</h4>
                <p>Ein kurzer Überblick über gespeicherte Werte. Änderungen machst du direkt in den jeweiligen Bereichen.</p></div>
              <button type="button" className="secondary" onClick={() => setReload(n => n + 1)}>Alle Komponenten neu prüfen</button>
            </div>
            {loadError ? <p role="alert">Inventurfehler: {loadError}</p> : null}
            {loading ? <p role="status">Runtime- und Modellinventar werden geladen …</p> : null}
            <dl className="yj-settings-summary">
              <div><dt>Chat</dt><dd>{settings.model_name}</dd></div>
              <div><dt>Whisper</dt><dd>{setupCheck.report?.stt.status === "available" ? "Setup verfügbar" : "Noch nicht verifiziert"}</dd></div>
              <div><dt>Sprachausgabe</dt><dd>{settings.tts_voice || settings.tts_engine}</dd></div>
              <div><dt>Speichern</dt><dd>{dirty ? "Ungespeicherte Auswahl vorhanden" : "Gespeichert"}</dd></div>
            </dl>
          </div>
        </section>}

      {section === "input" && <section className="settings-focus" aria-labelledby="settings-input-title">
        <div className="settings-inline-heading"><h3 id="settings-input-title">Spracheingabe</h3>
          <span className="settings-pill">{setupCheck.report?.stt.status === "available" ? "Whisper bereit laut Setup" : "Whisper nicht bestätigt"}</span>
        </div>
        <p>Prüfe zuerst das Mikrofon. Der Hardwaretest funktioniert auch dann, wenn Whisper noch nicht installiert ist.</p>
        <MicrophoneSettings selectedId={selectedMicId} onSelect={onSelectMic} voiceActive={voiceActive}
          onDeviceUnavailable={() => { setMicHardwareTested(false); onMicUnavailable(); }}
          sttAvailable={setupCheck.report?.stt.status === "available"}
          onStartVoiceTest={onStartVoiceTest} voiceStage={voiceStage}
          onHardwareTested={setMicHardwareTested} />
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
          <div className="settings-inline-heading">
            <h4>Installierte Whisper-Modelle</h4>
            <button type="button" className="secondary" onClick={() => openInstaller("whisper", null)}>
              Whisper installieren
            </button>
          </div>
          {inventoryStatus === "error" ? <p role="alert">Whisper-Inventur konnte nicht geladen werden.</p> : null}
          {inventoryStatus === "ready" && whisper.length === 0
            ? <p role="status">Keine lokal installierten Whisper-Modelldateien gefunden.</p> : null}
          <div className="yj-settings-choice-grid" aria-label="Installierte Whisper-Modelle">
            {whisper.map(item => <article className="yj-settings-choice" key={item.path}
              data-selected={draft.whisper_model_path === item.path}>
              <span className="yj-settings-card-eyebrow">Datei vorhanden · Inferenz ungeprüft</span>
              <strong>{item.name}</strong>
              <span>{item.path === settings.whisper_model_path ? "Gespeichert · aktiv" : "Installiert"}</span>
              <button type="button" className="secondary" aria-pressed={draft.whisper_model_path === item.path}
                onClick={() => change({ whisper_model_path: item.path })}>
                {draft.whisper_model_path === item.path ? "Ausgewählt" : "Modell wählen"}
              </button>
            </article>)}
          </div>
          <div className="settings-inline-heading"><h4>Weitere Whisper-Varianten</h4>
            <span className="settings-hint">Offizieller SetupInstaller-Katalog</span>
          </div>
          {catalogError ? <p role="alert">{catalogError}</p> : null}
          {!installOptions ? <p role="status">Installationsoptionen laden oder aktuell nicht verfügbar.</p> : null}
          <div className="yj-settings-choice-grid" aria-label="Installierbare Whisper-Modelle">
            {installOptions?.whisper_models.filter(name => !whisper.some(item => item.name === name))
              .map(name => <article className="yj-settings-choice" key={name}>
                <span className="yj-settings-card-eyebrow">Installierbar · nicht installiert</span>
                <strong>{name}</strong>
                <span>Modellvariante aus bestehendem Whisper-Installer. Bedarf abhängig vom Gerät.</span>
                <button type="button" className="secondary" onClick={() => openInstaller("whisper", name)}>
                  {name} installieren
                </button>
              </article>)}
          </div>
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
        <div className="settings-inline-heading">
          <h4>Installierte Chat-Modelle</h4>
          <button type="button" className="secondary" onClick={() => openInstaller("chat", null)}>
            Weitere Modelle installieren
          </button>
        </div>
        {inventory?.ollama.status !== "online" && !loading
          ? <p role="status">Ohne aktuelle Ollama-Verbindung können keine installierten Modelle bestätigt werden.</p> : null}
        {inventory?.ollama.status === "online" && installedChat.length === 0 && search.trim()
          ? <p role="status">Kein installiertes Modell passt zur Suche. Filter entfernen oder Katalog öffnen.</p> : null}
        <div className="yj-settings-choice-grid" aria-label="Installierte Ollama-Modelle">
          {installedChat.map(model => <article className="yj-settings-choice" key={model.digest + model.name}
            data-selected={draft.model_name === model.name}>
            <span className="yj-settings-card-eyebrow">Installiert · Inferenz ungeprüft</span>
            <strong>{model.name}</strong>
            <span>{gigabytes(model.size_bytes)}{model.name === settings.model_name ? " · Aktiv gespeichert" : ""}</span>
            <button type="button" className="secondary" aria-pressed={draft.model_name === model.name}
              onClick={() => change({ model_name: model.name })}>
              {draft.model_name === model.name ? "Ausgewählt" : "Modell wählen"}
            </button>
          </article>)}
        </div>
        <div className="settings-inline-heading">
          <h4>Weitere Modelle aus dem geprüften Katalog</h4>
          <span className="settings-hint">Katalogeintrag bedeutet nicht installiert</span>
        </div>
        {catalogError ? <p role="alert">{catalogError}</p> : null}
        <div className="yj-settings-choice-grid" aria-label="Installierbare Chat-Modelle">
          {chatCatalog.slice(0, 9).map(item => <article className="yj-settings-choice" key={item.id}>
            <span className="yj-settings-card-eyebrow">Katalog · installierbar, nicht installiert</span>
            <strong>{item.display_name}</strong>
            <span>{item.runtime.model_id}</span>
            <span>{gigabytes(item.acquisition.approximate_download_bytes)} · Quelle: {item.source.publisher}</span>
            <button type="button" className="secondary" onClick={() => openInstaller("chat", item.runtime.model_id)}>
              Installation vorbereiten
            </button>
          </article>)}
        </div>
        {chatCatalog.length > 9 ? <p>Weitere {chatCatalog.length - 9} Einträge im Modellkatalog der Installation.</p> : null}
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
        {!usingSay && <>
          <div className="settings-inline-heading"><h4>Installierte Stimmenbibliothek</h4>
            <button type="button" className="secondary" onClick={() => openInstaller("voice", null)}>
              Stimmen installieren
            </button>
          </div>
          {inventoryStatus === "ready" && voices.length === 0
            ? <p role="status">Keine vollständigen Piper-Modell-/Konfigurationspaare gefunden.</p> : null}
          <div className="yj-settings-choice-grid" aria-label="Installierte Piper-Stimmen">
            {voices.map(voice => <article className="yj-settings-choice" key={voice.path}
              data-selected={draft.tts_model_path === voice.path}>
              <span className="yj-settings-card-eyebrow">Installiert · Modell &amp; Konfiguration vorhanden</span>
              <strong>{voice.name}</strong>
              <span>{settings.tts_model_path === voice.path && settings.tts_engine === "piper" ? "Aktiv gespeichert" : "Audio ungeprüft"}</span>
              <button type="button" className="secondary" aria-pressed={draft.tts_model_path === voice.path}
                onClick={() => change({ tts_engine: "piper", tts_model_path: voice.path, tts_voice: voice.name })}>
                {draft.tts_model_path === voice.path ? "Ausgewählt" : "Stimme wählen"}
              </button>
            </article>)}
          </div>
          <div className="settings-inline-heading">
            <h4>Weitere Stimmen</h4>
            <span className="settings-hint">Nur Einträge des vorhandenen Piper-SetupInstallers</span>
          </div>
          <label className="settings-search">Stimmenbibliothek durchsuchen
            <input value={voiceSearch} onChange={event => setVoiceSearch(event.target.value)}
              placeholder="Sprache, Sprecher oder Modell-ID" />
          </label>
          {catalogError ? <p role="alert">{catalogError}</p> : null}
          {!installOptions ? <p role="status">Stimmenkatalog nicht geladen. Neu laden versuchen.</p> : null}
          <div className="yj-settings-choice-grid" aria-label="Installierbare Piper-Stimmen">
            {moreVoices.filter(option => !voices.some(voice => voice.name === option.id))
              .slice(0, 12).map(option => <article className="yj-settings-choice" key={option.id}>
              <span className="yj-settings-card-eyebrow">Installierbar · nicht installiert</span>
              <strong>{option.name}</strong>
              <span>{option.id}</span>
              <button type="button" className="secondary" onClick={() => openInstaller("voice", option.id)}>
                Stimme installieren
              </button>
            </article>)}
          </div>
          {moreVoices.length > 12 ? <p role="status">Weitere Stimmen durch die Suche filtern.</p> : null}
        </>}
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
          <button type="button" className="secondary" aria-expanded={installerOpen}
            onClick={() => installerOpen ? setInstallerOpen(false) : openInstaller()}>
            {installerOpen ? "Einrichtung schließen" : "Weitere Modelle & Stimmen installieren"}
          </button>
          <p className="settings-hint">Installationen verwenden ausschließlich SetupInstaller mit echten Fortschritts-, Fehler- und Abbruchzuständen. Es gibt keine automatischen Downloads.</p>
        </div>
      </div>
    </div>
    <div className="settings-footer yj-settings-savebar">
      <div className="mic-test-actions">
        <button type="button" onClick={() => void saveDraft()} disabled={!dirty || saveState === "saving"}>
          {saveState === "saving" ? "Speichere …" : "Änderungen speichern"}
        </button>
        <button type="button" className="secondary" onClick={discardDraft} disabled={!dirty || saveState === "saving"}>
          Verwerfen
        </button>
      </div>
      <span role="status">
        {saveState === "saving" ? "Speichere Einstellungen …" :
          saveState === "error" ? "Speichern fehlgeschlagen" :
          dirty ? "Nicht gespeicherte Änderungen" : "Einstellungen gespeichert"}
        {" · Aktiv: "}{settings.model_name}
      </span>
      {saveError ? <p role="alert" className="installation-error">{saveError}</p> : null}
    </div>
  </section>;
}
