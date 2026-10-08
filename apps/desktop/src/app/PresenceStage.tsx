import type { CSSProperties } from "react";

export type PresenceMode = "idle" | "thinking" | "speaking";
const PARTICLES = Array.from({ length: 14 }, (_, index) => index);
const RUN_LABELS: Record<string, string> = {
  received: "Anfrage empfangen", thinking: "Anfrage wird verarbeitet",
  approval_required: "Freigabe benötigt", executing: "Aktion wird ausgeführt",
  done: "Vorgang abgeschlossen", error: "Aktion fehlgeschlagen"
};
export function runStateLabel(state: string): string { return Object.prototype.hasOwnProperty.call(RUN_LABELS, state) ? RUN_LABELS[state] : "Statusmeldung"; }

// Symbolic presence, not an audio-amplitude meter or a backend health indicator.
export function PresenceCore({ mode = "idle" }: { mode?: PresenceMode }) {
  return <div className={`conversation-orb ${mode}`} aria-hidden="true">
    <div className="conversation-orb-aurora" />
    <div className="conversation-orb-grid" />
    <div className="conversation-orb-rings"><span /><span /><span /><span /></div>
    <div className="conversation-orb-core-shell"><div className="conversation-orb-core" /><div className="conversation-orb-core-glint" /></div>
    <div className="conversation-orb-wave"><span /><span /><span /><span /><span /></div>
    <div className="conversation-orb-particles">{PARTICLES.map((index) => <span key={index} style={{ "--particle-index": index } as CSSProperties} />)}</div>
  </div>;
}

export function PresenceStage({ mode, microphoneActive, latestEvent }: {
  mode: PresenceMode; microphoneActive: boolean;
  latestEvent?: { id: string; state: string; timestamp: string };
}) {
  return <section className="presence-stage" data-mode={mode} aria-label="Jarvis Präsenz">
    <p className="eyebrow">Dein persönlicher Assistent</p>
    <div className="presence-orbit"><PresenceCore mode={mode} /></div>
    <div className="presence-caption">
      <h2>Jarvis<span aria-hidden="true">.</span></h2>
      <p role="status">{mode === "speaking" ? "Sprachausgabe aktiv oder vorgemerkt" : mode === "thinking" ? "Anfrage aktiv" : "Im Ruhezustand"}</p>
      <span className="microphone-status" data-active={microphoneActive}>{microphoneActive ? "Mikrofon aktiv" : "Mikrofon aus"}</span>
    </div>
    {latestEvent ? <div className="presence-event" key={latestEvent.id} data-state={latestEvent.state}>
      <small>Letztes Agent-Ereignis · {new Date(latestEvent.timestamp).toLocaleTimeString()}</small>
      <p>{runStateLabel(latestEvent.state)}</p>
    </div> : null}
  </section>;
}
