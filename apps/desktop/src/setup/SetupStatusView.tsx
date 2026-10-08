import type { SetupCheck } from "./types";
import { ModelCatalogBrowser } from "./ModelCatalogBrowser";
import { HardwareProfileView } from "./HardwareProfileView";

export const SETUP_LABELS: Record<SetupCheck["state"], string> = {
  checking: "Einrichtung wird geprüft",
  needs_setup: "Chat braucht noch Einrichtung",
  ready: "Jarvis ist bereit",
  degraded: "Text-Chat bereit · Voice eingeschränkt",
  error: "Einrichtung konnte nicht geprüft werden"
};

const REASONS: Record<string, string> = {
  chat_model_present: "Das konfigurierte Chat-Modell ist vorhanden. Diese Statusprüfung führt keine Inferenz aus.",
  chat_model_missing: "Das konfigurierte Chat-Modell fehlt am Modell-Endpunkt.",
  chat_model_not_configured: "Es ist noch kein Chat-Modell konfiguriert.",
  ollama_unreachable: "Der konfigurierte Ollama-Endpunkt ist nicht erreichbar.",
  ollama_endpoint_invalid: "Der konfigurierte Ollama-Endpunkt ist ungültig.",
  ollama_response_invalid: "Die Modellliste konnte nicht zuverlässig gelesen werden.",
  path_not_configured: "Es ist noch kein Modellpfad eingerichtet.",
  model_file_present: "Die Modelldatei ist vorhanden. Erkennung und Audio wurden nicht getestet.",
  model_file_missing: "Die konfigurierte Modelldatei fehlt.",
  model_file_invalid: "Der Modellpfad zeigt auf keine nicht-leere Datei.",
  model_file_unreadable: "Der Modellpfad konnte nicht zuverlässig geprüft werden.",
  voice_unverified: "Voice lässt sich hier nicht zuverlässig prüfen. Es wurde kein Audio gestartet.",
  voice_verified_during_setup: "Diese Stimme wurde bei der Einrichtung erfolgreich synthetisiert und ausgegeben."
};
const COMPONENT_LABELS = { available: "Vorhanden", missing: "Fehlt", unreachable: "Nicht erreichbar", unknown: "Ungeprüft", error: "Prüfung fehlgeschlagen" };

export function SetupStatusView({ check }: { check: SetupCheck }) {
  const items = [["chat_model", "Chat-Modell", "Erforderlich"], ["stt", "Spracheingabe · Modell", "Optional"], ["tts", "Sprachausgabe", "Optional"]] as const;
  return (
    <ul className="setup-components">
      {items.map(([key, title, requirement]) => {
        const component = check.report?.[key];
        return (
          <li key={key} data-status={component?.status || "unknown"}>
            <div><h3>{title}</h3><small>{requirement}</small></div>
            <strong>{component ? COMPONENT_LABELS[component.status] : check.state === "checking" ? "Wird geprüft" : "Nicht geprüft"}</strong>
            <p>{component ? REASONS[component.reason] || "Der Status ist nicht zuverlässig bestimmt."
              : check.state === "error" ? "Kein verlässliches Prüfergebnis. Bitte erneut prüfen."
              : check.backendReachable ? "Warte auf das Prüfergebnis." : "Warte auf die Verbindung zum lokalen Agenten."}</p>
          </li>
        );
      })}
    </ul>
  );
}

export function SetupNotice({ check, onRetry }: { check: SetupCheck; onRetry: () => void }) {
  return (
    <aside className="setup-notice" data-setup-state={check.state} aria-label="Einrichtungsstatus">
      <details>
        <summary aria-label={SETUP_LABELS[check.state]}><span role="status">{SETUP_LABELS[check.state]}</span></summary>
        <SetupStatusView check={check} />
        <p>Die Prüfung verändert keine Settings. Voice ist optional; vorhandene Dateien sind kein Audio-Funktionstest.</p>
        <ModelCatalogBrowser />
        <HardwareProfileView />
      </details>
      <button type="button" className="secondary" disabled={check.state === "checking"} onClick={onRetry}>Erneut prüfen</button>
    </aside>
  );
}
