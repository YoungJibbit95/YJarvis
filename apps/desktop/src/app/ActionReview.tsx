import type { Approval } from "@jarvis/shared-types";

const ACTIONS: Record<string, string> = {
  open_url: "Website öffnen", open_app: "App öffnen", file_read: "Datei lesen",
  file_write: "Datei schreiben", clipboard_read: "Zwischenablage lesen",
  clipboard_write: "Zwischenablage schreiben", reminder_create: "Erinnerung erstellen",
  reminder_list: "Erinnerungen lesen", calendar_create_event: "Kalendereintrag erstellen",
  calendar_list_events: "Kalendereinträge lesen", notes_create: "Notiz erstellen",
  notes_search: "Notizen durchsuchen", mail_create_draft: "E-Mail-Entwurf erstellen",
  messages_send: "Nachricht senden", contacts_search: "Kontakte durchsuchen",
  music_control: "Musik steuern", raycast_open: "Raycast öffnen", raycast_run_command: "Raycast-Befehl ausführen"
};
const FIELDS: Record<string, string> = { url: "Adresse", path: "Dateipfad", content: "Inhalt", mode: "Schreibmodus", app_name: "App", title: "Titel", text: "Text", to: "Empfänger", body: "Nachricht" };
function valueText(value: unknown): string { return typeof value === "string" ? value : JSON.stringify(value, null, 2); }

export function ActionReview({ approval, onDecide }: { approval: Approval; onDecide: (id: string, decision: "approve" | "deny") => void }) {
  const known = Object.prototype.hasOwnProperty.call(ACTIONS, approval.tool_name);
  return <article className="approval-card">
    <header className="action-review-heading">
      <span className="action-review-mark" aria-hidden="true">↗</span>
      <div><p className="eyebrow">Deine Entscheidung</p><h3>{known ? ACTIONS[approval.tool_name] : "Aktion prüfen"}</h3></div>
      <span className="approval-pending">Freigabe ausstehend</span>
    </header>
    <p>{known ? "Jarvis schlägt diese Aktion mit den folgenden Angaben vor." : `Tool: ${approval.tool_name}. Für diesen Aktionstyp gibt es keine ausführlichere Beschreibung.`}</p>
    <dl className="action-inputs">{Object.entries(approval.tool_input).map(([key, value]) => <div key={key}>
      <dt>{Object.prototype.hasOwnProperty.call(FIELDS, key) ? FIELDS[key] : key}</dt><dd>{valueText(value)}</dd>
    </div>)}</dl>
    {Object.keys(approval.tool_input).length === 0 ? <p>Keine Eingabedaten übermittelt.</p> : null}
    <details className="technical-details"><summary>Vollständige Aktionsdaten</summary>
      <dl><dt>Tool</dt><dd><code>{approval.tool_name}</code></dd><dt>Run-ID</dt><dd><code>{approval.run_id}</code></dd><dt>Freigabe-ID</dt><dd><code>{approval.id}</code></dd></dl>
      <pre>{JSON.stringify(approval.tool_input, null, 2)}</pre>
    </details>
    <div className="approval-actions">
      <button type="button" className="approval-confirm" onClick={() => onDecide(approval.id, "approve")}>Freigeben</button>
      <button type="button" className="secondary" onClick={() => onDecide(approval.id, "deny")}>Ablehnen</button>
    </div>
  </article>;
}
