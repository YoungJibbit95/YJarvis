import { useCallback, useEffect, useRef, useState } from "react";
import App from "../App";
import { fetchSetupStatus, waitForBackend } from "../api";
import { AppHeader } from "../app/AppShell";
import { SETUP_LABELS, SetupStatusView } from "./SetupStatusView";
import type { SetupCheck } from "./types";
import { ModelCatalogBrowser } from "./ModelCatalogBrowser";
import { HardwareProfileView } from "./HardwareProfileView";
import { PresenceCore } from "../app/PresenceStage";

export function SetupGate() {
  const [check, setCheck] = useState<SetupCheck>({ state: "checking", backendReachable: false });
  const [enteredApp, setEnteredApp] = useState(false);
  const generation = useRef(0);
  const pending = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    const request = ++generation.current;
    let backendReachable = false;
    setCheck({ state: "checking", backendReachable: false });
    const deadline = window.setTimeout(() => controller.abort(), 50_000);
    try {
      // Reuse the existing desktop connection probe; App starts only after this gate.
      await waitForBackend(45_000, controller.signal);
      if (request !== generation.current) return;
      backendReachable = true;
      setCheck({ state: "checking", backendReachable });
      const report = await fetchSetupStatus(controller.signal);
      if (request !== generation.current) return;
      setCheck({ state: report.state, backendReachable, report });
      if (report.state === "ready" || report.state === "degraded") setEnteredApp(true);
    } catch {
      if (request === generation.current) setCheck({ state: "error", backendReachable });
    } finally {
      window.clearTimeout(deadline);
    }
  }, []);

  useEffect(() => {
    void refresh();
    return () => { generation.current++; pending.current?.abort(); };
  }, [refresh]);

  // Once entered, keep App mounted during rechecks so drafts, approvals and sessions survive.
  if (enteredApp) return <App setupCheck={check} onRecheckSetup={refresh} />;

  return (
    <div className="setup-screen" data-setup-state={check.state}>
      <AppHeader />
      <main className="setup-first-run" aria-labelledby="setup-title" aria-busy={check.state === "checking"}>
        <div className="activation-hero">
          <div className="activation-presence" aria-hidden="true">
            <PresenceCore mode={check.state === "checking" ? "thinking" : "idle"} />
          </div>
          <div className="activation-copy">
            <p className="eyebrow">Dein persönlicher Assistent · Einrichtung</p>
            <h2 id="setup-title">{check.state === "needs_setup" ? <>Dein Jarvis.<br /><span>Dein nächster Schritt.</span></> : SETUP_LABELS[check.state]}</h2>
            <p className="setup-intro" role="status">{check.state === "needs_setup"
              ? "Jarvis braucht noch lokale AI-Komponenten. Hier siehst du, was vorhanden ist und was noch fehlt."
              : check.state === "error" ? "Es gibt noch kein verlässliches Ergebnis. Du kannst die Verbindung prüfen und es erneut versuchen."
              : "Jarvis liest die vorhandene Konfiguration und prüft deinen Modell-Endpunkt."}</p>
            <div className="setup-actions">
              <button type="button" disabled={check.state === "checking"} onClick={() => void refresh()}>Erneut prüfen</button>
              {check.backendReachable ? <button type="button" className="secondary" onClick={() => setEnteredApp(true)}>Später · App ansehen</button> : null}
            </div>
            <p className="setup-footnote">Ohne bestätigtes Chat-Modell bleibt der Chat gesperrt. Einstellungen und Freigaben bleiben in der App erreichbar.</p>
          </div>
        </div>
        <div className="activation-capabilities">
          <div className="section-heading"><p className="eyebrow">Was schon vorhanden ist</p><h3>Die Bausteine deines Assistenten</h3></div>
          <SetupStatusView check={check} />
        </div>
        <details className="setup-explanation technical-details"><summary>Was wird bei der Einrichtung geprüft?</summary>
          <p>Diese Prüfung installiert nichts und ändert keine Einstellungen. Sie fragt nur den konfigurierten Modell-Endpunkt ab und prüft vorhandene Modellpfade.</p>
          <p>Du kannst die App ansehen und vorhandene Komponenten in den Einstellungen eintragen. Eine geführte Modellinstallation ist hier noch nicht verfügbar.</p>
        </details>
        <ModelCatalogBrowser />
        <HardwareProfileView />
      </main>
    </div>
  );
}
