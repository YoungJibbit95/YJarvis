import { useEffect, useState } from "react";
import { fetchHardwareProfile } from "../api";
import type { HardwareProfile } from "./hardwareProfile";

export type HardwareViewState = { status: "loading" } | { status: "error" } | { status: "loaded"; profile: HardwareProfile };
const PLATFORMS = { windows: "Windows", macos: "macOS", linux: "Linux", unknown: "Unbekannt" };
const ARCHITECTURES = { x86_64: "x86-64", arm64: "ARM64", other: "Andere Architektur", unknown: "Unbekannt" };
const numbers = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 });
function bytes(value: number | null): string {
  if (value === null) return "Unbekannt";
  if (value > 0 && value < 1024 ** 3 / 10) return "< 0,1 GiB";
  return `${numbers.format(value / 1024 ** 3)} GiB`;
}

export function HardwareProfileContent({ state, onRetry }: { state: HardwareViewState; onRetry: () => void }) {
  if (state.status === "loading") return <p role="status">Systemdaten werden gelesen …</p>;
  if (state.status === "error") return <div>
    <p role="alert">Die Systemdaten konnten nicht zuverlässig gelesen werden. Modellübersicht und Einrichtungsstatus bleiben unverändert.</p>
    <button type="button" className="secondary" onClick={onRetry}>Systemdaten erneut lesen</button>
  </div>;
  const profile = state.profile;
  return <>
    <dl className="hardware-facts">
      <div><dt>Betriebssystem</dt><dd>{PLATFORMS[profile.platform]}</dd></div>
      <div><dt>CPU-Architektur</dt><dd>{ARCHITECTURES[profile.architecture]}</dd></div>
      <div><dt>Logische CPU-Kerne</dt><dd>{profile.logical_cpu_count === null ? "Unbekannt" : numbers.format(profile.logical_cpu_count)}</dd></div>
      <div><dt>RAM gesamt</dt><dd>{bytes(profile.total_memory_bytes)}</dd></div>
      <div><dt>Frei am App-Datenstandort</dt><dd>{bytes(profile.available_storage_bytes)}</dd></div>
    </dl>
    <p>Momentaufnahme des lokalen Agenten. Speicherplatz bezieht sich auf den bestehenden App-Datenordner, nicht auf einen festgelegten Modell-Installationsordner. Unbekannte Werte werden nicht geschätzt.</p>
  </>;
}

function HardwareLoader() {
  const [state, setState] = useState<HardwareViewState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const deadline = window.setTimeout(() => controller.abort(), 8_000);
    setState({ status: "loading" });
    void fetchHardwareProfile(controller.signal).then((profile) => {
      if (active) setState({ status: "loaded", profile });
    }).catch(() => { if (active) setState({ status: "error" }); })
      .finally(() => window.clearTimeout(deadline));
    return () => { active = false; controller.abort(); window.clearTimeout(deadline); };
  }, [attempt]);
  return <HardwareProfileContent state={state} onRetry={() => setAttempt((value) => value + 1)} />;
}

export function HardwareProfileView() {
  const [open, setOpen] = useState(false);
  return <details className="setup-hardware" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>Dieses System</summary>
    {open ? <HardwareLoader /> : null}
  </details>;
}
