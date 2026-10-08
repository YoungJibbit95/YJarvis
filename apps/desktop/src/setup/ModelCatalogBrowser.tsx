import { useEffect, useState } from "react";
import { fetchModelCatalog } from "../api";
import type { ModelCatalogEntry, ModelSource } from "./modelCatalog";

export type CatalogBrowseState = { status: "loading" } | { status: "error" } | { status: "loaded"; entries: ModelCatalogEntry[] };
const CATEGORIES = { chat: "Chat", speech_to_text: "Spracheingabe", text_to_speech: "Sprachausgabe" };
const BACKENDS = { ollama: "Ollama", whisper_cpp: "whisper.cpp", piper: "Piper" };
const ROLES = { chat: "Denken & Dialog", speech_to_text: "Dich verstehen", text_to_speech: "Mit dir sprechen" };
const MARKS = { chat: "C", speech_to_text: "STT", text_to_speech: "TTS" };
const numbers = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 });

function SourceInfo({ source }: { source: ModelSource }) {
  // Plain text until Electron has an explicitly reviewed external-navigation boundary.
  return <span className="catalog-source">{source.publisher} · geprüft am {source.checked_on}<code>{source.url}</code></span>;
}

export function ModelCatalogContent({ state, onRetry }: { state: CatalogBrowseState; onRetry: () => void }) {
  if (state.status === "loading") return <p role="status">Modellübersicht wird geladen …</p>;
  if (state.status === "error") return <div className="catalog-error">
    <p role="alert">Die Modellübersicht konnte nicht zuverlässig geladen werden. Dein Einrichtungsstatus bleibt unverändert.</p>
    <button type="button" className="secondary" onClick={onRetry}>Modellübersicht erneut laden</button>
  </div>;
  return <ul className="catalog-grid">
    {state.entries.map((model) => {
      const size = model.acquisition.approximate_download_bytes;
      return <li key={model.id} className="catalog-card" data-category={model.category}>
        <div className="catalog-identity">
          <span className="catalog-mark" aria-hidden="true">{MARKS[model.category]}</span>
          <div><p>{ROLES[model.category]}</p><span className="catalog-category">{CATEGORIES[model.category]}</span></div>
        </div>
        <div className="catalog-description">
          <h3>{model.display_name}</h3>
          <p>{model.description}</p>
        </div>
        <dl className="catalog-facts">
          <div><dt>Herausgeber</dt><dd>{model.publisher}</dd></div>
          {size !== null ? <div><dt>Downloadgröße · ungefähr</dt><dd>{numbers.format(size / (size >= 1e9 ? 1e9 : 1e6))} {size >= 1e9 ? "GB" : "MB"}</dd></div> : null}
          {model.licenses.map((license) => <div key={license.scope}>
            <dt>{license.scope === "model" ? "Modelllizenz" : "Datensatzlizenz"}</dt>
            <dd>{license.name ?? "Nicht eindeutig angegeben"}</dd>
          </div>)}
        </dl>
        <details className="catalog-details">
          <summary>Quellen und technische Details</summary>
          <dl className="catalog-facts">
            <div><dt>Backend</dt><dd>{BACKENDS[model.runtime.backend]}</dd></div>
            {model.context_window_tokens !== null ? <div><dt>Kontext laut Herausgeber</dt><dd>{numbers.format(model.context_window_tokens)} Tokens</dd></div> : null}
            <div><dt>Katalog-ID</dt><dd><code>{model.id}</code></dd></div>
            <div><dt>Modell-ID</dt><dd><code>{model.model_id}</code></dd></div>
            <div><dt>Backend-Modell-ID</dt><dd><code>{model.runtime.model_id}</code></dd></div>
            {model.publisher_quality_label !== null ? <div><dt>Variantenlabel des Herausgebers</dt><dd>{model.publisher_quality_label}</dd></div> : null}
            <div><dt>Modellquelle</dt><dd><SourceInfo source={model.source} /></dd></div>
            <div><dt>Bezugsquelle · {model.acquisition.mechanism === "ollama_library" ? "Ollama Library" : "Hugging Face"}</dt><dd><SourceInfo source={model.acquisition.source} /></dd></div>
            {model.licenses.map((license) => <div key={license.scope}>
              <dt>Lizenzquelle · {license.scope === "model" ? "Modell" : "Datensatz"}</dt><dd><SourceInfo source={license.source} /></dd>
            </div>)}
          </dl>
          <p>Die Angaben beschreiben die Quelle. Sie bestätigen keine Eignung für jeden Einsatzzweck.</p>
        </details>
      </li>;
    })}
  </ul>;
}

function CatalogLoader() {
  const [state, setState] = useState<CatalogBrowseState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const deadline = window.setTimeout(() => controller.abort(), 8_000);
    setState({ status: "loading" });
    void fetchModelCatalog(controller.signal).then((entries) => {
      if (active) setState({ status: "loaded", entries });
    }).catch(() => { if (active) setState({ status: "error" }); })
      .finally(() => window.clearTimeout(deadline));
    return () => { active = false; controller.abort(); window.clearTimeout(deadline); };
  }, [attempt]);
  return <ModelCatalogContent state={state} onRetry={() => setAttempt((value) => value + 1)} />;
}

export function ModelCatalogBrowser() {
  const [open, setOpen] = useState(false);
  return <details className="model-catalog" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>Unterstützte lokale Modelle</summary>
    <p>Hier siehst du, welche Modelle Jarvis kennt. Diese Übersicht zeigt keinen Installationsstatus und keine Empfehlung für deinen Computer. Das Ansehen ändert keine Einstellungen.</p>
    {open ? <CatalogLoader /> : null}
  </details>;
}
