import { useEffect, useState } from "react";
import { fetchAcceleratorProfile } from "../api";
import type { AcceleratorProfile } from "./acceleratorProfile";

export type AcceleratorViewState = { status: "loading" } | { status: "error" } | { status: "loaded"; profile: AcceleratorProfile };
const CLASSIFICATIONS = { hardware: "Hardware-Adapter", software: "Software-Adapter", unknown: "Adaptertyp unbekannt" };
const numbers = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 });
function bytes(value: number | null): string {
  if (value === null) return "Unbekannt";
  if (value > 0 && value < 1024 ** 3 / 10) return "< 0,1 GiB";
  return `${numbers.format(value / 1024 ** 3)} GiB`;
}

export function AcceleratorProfileContent({ state, onRetry }: { state: AcceleratorViewState; onRetry: () => void }) {
  if (state.status === "loading") return <p role="status">Grafikdetails werden gelesen …</p>;
  if (state.status === "error" || state.profile.status === "unknown") return <div>
    <p role="alert">Grafikdetails konnten nicht zuverlässig gelesen werden. Systemdaten, Modellübersicht und Einrichtungsstatus bleiben unverändert.</p>
    <button type="button" className="secondary" onClick={onRetry}>Grafikdetails erneut lesen</button>
  </div>;
  if (state.profile.status === "unsupported") return <p>Grafikdetails werden auf diesem Betriebssystem noch nicht unterstützt.</p>;
  if (state.profile.adapters.length === 0) return <p>Windows meldet keine Grafikadapter.</p>;
  return <>
    <ul className="accelerator-list">
      {state.profile.adapters.map((adapter, index) => <li key={index} data-classification={adapter.classification}>
        <h4>{adapter.display_name}</h4>
        <p>{CLASSIFICATIONS[adapter.classification]}</p>
        <dl className="hardware-facts">
          <div><dt>Dedizierter Grafikspeicher</dt><dd>{bytes(adapter.dedicated_video_memory_bytes)}</dd></div>
          <div><dt>Gemeinsam nutzbarer Systemspeicher · Obergrenze</dt><dd>{bytes(adapter.shared_system_memory_bytes)}</dd></div>
        </dl>
      </li>)}
    </ul>
    <p>Von Windows gemeldete Momentaufnahme. Gemeinsam nutzbarer Systemspeicher ist eine Obergrenze, kein zusätzlicher dedizierter Grafikspeicher. Die Werte sagen nichts über Modell-Eignung oder Geschwindigkeit aus.</p>
  </>;
}

export function AcceleratorProfileView() {
  const [state, setState] = useState<AcceleratorViewState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const deadline = window.setTimeout(() => controller.abort(), 8_000);
    setState({ status: "loading" });
    void fetchAcceleratorProfile(controller.signal).then((profile) => {
      if (active) setState({ status: "loaded", profile });
    }).catch(() => { if (active) setState({ status: "error" }); })
      .finally(() => window.clearTimeout(deadline));
    return () => { active = false; controller.abort(); window.clearTimeout(deadline); };
  }, [attempt]);
  return <section className="setup-accelerators" aria-label="Grafik / Beschleuniger">
    <h3>Grafik / Beschleuniger</h3>
    <AcceleratorProfileContent state={state} onRetry={() => setAttempt((value) => value + 1)} />
  </section>;
}
