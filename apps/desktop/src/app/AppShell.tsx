import type { ReactNode } from "react";
import { InterfaceIcon } from "./InterfaceIcon";

export type TabId = "chat" | "approvals" | "settings" | "smarthome";

type RuntimeValues = {
  core: string;
  voiceInput: string;
  uiRender: string;
  replyMode: string;
  model: string;
  stt: string;
  session: string;
  client: string;
};

type NavigationProps = {
  activeTab: TabId;
  onNavigate: (tab: TabId) => void;
};

type AppShellProps = NavigationProps & {
  runtime: RuntimeValues;
  onOpenCommands: () => void;
  children: ReactNode;
  notice?: ReactNode;
};

const NAVIGATION: ReadonlyArray<{ id: TabId; label: string }> = [
  { id: "chat", label: "Chat" },
  { id: "approvals", label: "Freigaben" },
  { id: "settings", label: "Einstellungen" },
  { id: "smarthome", label: "Smart Home" }
];

function GlobalCommandTrigger({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      type="button"
      className="secondary shell-command"
      aria-keyshortcuts="Control+k Meta+k"
      onClick={onOpen}
    >
      Kommandos
      <kbd aria-hidden="true">Ctrl / ⌘ K</kbd>
    </button>
  );
}

export function AppHeader({ onOpenCommands }: { onOpenCommands?: () => void }) {
  return (
    <header className="shell-header">
      <div className="shell-identity">
        <span className="shell-emblem" aria-hidden="true"><span /></span>
        <div>
          <h1>YJARVIS</h1>
          <p>Persönlich. Lokal. Unter deiner Kontrolle.</p>
        </div>
      </div>
      {onOpenCommands ? <GlobalCommandTrigger onOpen={onOpenCommands} /> : null}
    </header>
  );
}

function RuntimeStatus({ values }: { values: RuntimeValues }) {
  const details = [
    ["Voice Input", values.voiceInput],
    ["Core", values.core],
    ["UI Render", values.uiRender],
    ["Reply Mode", values.replyMode],
    ["Model", values.model],
    ["STT", values.stt],
    ["Session", values.session],
    ["Client", values.client]
  ];

  return (
    <details className="shell-runtime">
      <summary>
        <span className="shell-runtime-label">Runtime-Diagnose</span>
      </summary>
      <dl className="shell-runtime-details">
        {details.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function PrimaryNavigation({ activeTab, onNavigate }: NavigationProps) {
  return (
    <nav className="shell-navigation" aria-label="Hauptnavigation">
      <p>Dein Raum</p>
      <div className="shell-navigation-items">
        {NAVIGATION.map(({ id, label }) => (
          <button
            key={id}
            id={`shell-nav-${id}`}
            type="button"
            className={activeTab === id ? "active" : "secondary"}
            aria-current={activeTab === id ? "page" : undefined}
            aria-controls="shell-content"
            onClick={() => onNavigate(id)}
          >
            <InterfaceIcon name={id} /><span>{label}</span>
          </button>
        ))}
      </div>
    </nav>
  );
}

export function AppShell({ activeTab, onNavigate, runtime, onOpenCommands, children, notice }: AppShellProps) {
  return (
    <div className="app-shell">
      <a className="shell-skip-link" href="#shell-content">Zum Inhalt</a>
      <AppHeader onOpenCommands={onOpenCommands} />
      <div className="shell-status-area">
        <RuntimeStatus values={runtime} />
        {notice}
      </div>
      <div className="shell-body">
        <PrimaryNavigation activeTab={activeTab} onNavigate={onNavigate} />
        <main id="shell-content" className="shell-content" tabIndex={-1} aria-labelledby={`shell-nav-${activeTab}`}>
          {children}
        </main>
      </div>
    </div>
  );
}
