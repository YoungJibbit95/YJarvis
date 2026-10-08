export type ConnectionState =
  | { phase: "starting" | "connecting" | "connected" | "reconnecting" }
  | { phase: "retry_wait"; seconds: number };
export type FailureKind = "chat" | "voice" | "action" | "session";
export type Failures = Partial<Record<FailureKind, { title: string; message: string }>>;

// Transport callbacks own this state. Assistant activity and diagnostic prose do not.
export function AppFeedback({ connection, failures, onDismiss }: {
  connection: ConnectionState;
  failures: Failures;
  onDismiss: (kind: FailureKind) => void;
}) {
  const interrupted = connection.phase === "retry_wait" || connection.phase === "reconnecting";
  const label = connection.phase === "connected" ? "Agent-Verbindung hergestellt"
    : connection.phase === "starting" ? "Session wird gestartet"
    : connection.phase === "connecting" ? "Agent-Verbindung wird aufgebaut"
    : connection.phase === "retry_wait" ? `Verbindung unterbrochen · Neuer Versuch in ${connection.seconds} s`
    : "Verbindung unterbrochen · Wiederverbindung läuft";
  return <section className="app-feedback" aria-label="Verbindung und Fehlermeldungen" tabIndex={-1}>
    <p className="connection-status" data-interrupted={interrupted} role="status" aria-atomic="true">{label}</p>
    <div className="failure-list" aria-label="Fehlermeldungen" tabIndex={Object.keys(failures).length ? 0 : undefined}>
      {(Object.entries(failures) as [FailureKind, NonNullable<Failures[FailureKind]>][]).map(([kind, failure]) =>
        <div className="action-failure" key={kind}>
          <div role="alert" aria-atomic="true"><strong>{failure.title}</strong><p>{failure.message}</p></div>
          <button type="button" className="secondary" aria-label={`${failure.title}: Hinweis schließen`} onClick={(event) => {
            // Keep keyboard focus in a stable region when its dismiss button disappears.
            event.currentTarget.closest<HTMLElement>(".app-feedback")?.focus();
            onDismiss(kind);
          }}>Schließen</button>
        </div>
      )}
    </div>
  </section>;
}
