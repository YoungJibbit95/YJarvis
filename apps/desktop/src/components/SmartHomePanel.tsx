import type { SmartHomeEntity } from "@jarvis/shared-types";

type SmartHomePanelProps = {
  entities: SmartHomeEntity[];
  onAction: (entityId: string, service: string) => void;
};

export default function SmartHomePanel({ entities, onAction }: SmartHomePanelProps) {
  const activeCount = entities.filter((entity) => entity.state === "on").length;

  return (
    <section className="grid h-full min-h-0 grid-cols-1 gap-4 lg:grid-cols-[1.25fr_0.75fr]">
      <div className="glass-panel min-h-0 overflow-hidden p-4">
        <header className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-xs uppercase tracking-[0.2em] text-jarvis-cyan">Smart Home Grid</h2>
          <span className="text-[10px] text-white/50">Template Provider</span>
        </header>

        <div className="custom-scrollbar h-full min-h-0 overflow-auto pr-1">
          <div className="grid gap-3 sm:grid-cols-2">
            {entities.map((entity) => (
              <article key={entity.id} className="rounded-xl border border-white/15 bg-white/5 p-3">
                <div className="mb-2 flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-white/90">{entity.name}</h3>
                    <p className="text-[10px] uppercase tracking-[0.12em] text-white/45">{entity.entity_type}</p>
                  </div>
                  <span
                    className={[
                      "rounded-full border px-2 py-0.5 text-[10px] uppercase",
                      entity.state === "on"
                        ? "border-jarvis-cyan/45 bg-jarvis-cyan/10 text-jarvis-cyan"
                        : "border-white/20 bg-white/5 text-white/60"
                    ].join(" ")}
                  >
                    {entity.state}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    className="rounded-md border border-white/15 bg-white/5 px-2 py-1.5 text-[10px] uppercase tracking-[0.12em] text-white/75 transition hover:border-jarvis-cyan/35"
                    onClick={() => onAction(entity.id, "toggle")}
                  >
                    Toggle
                  </button>
                  <button
                    type="button"
                    className="rounded-md border border-jarvis-cyan/35 bg-jarvis-cyan/10 px-2 py-1.5 text-[10px] uppercase tracking-[0.12em] text-jarvis-cyan transition hover:bg-jarvis-cyan/20"
                    onClick={() => onAction(entity.id, "turn_on")}
                  >
                    On
                  </button>
                  <button
                    type="button"
                    className="rounded-md border border-white/15 bg-white/5 px-2 py-1.5 text-[10px] uppercase tracking-[0.12em] text-white/75 transition hover:border-jarvis-cyan/35"
                    onClick={() => onAction(entity.id, "turn_off")}
                  >
                    Off
                  </button>
                </div>
              </article>
            ))}
          </div>

          {!entities.length ? (
            <p className="mt-2 text-sm text-white/60">Keine Entities gefunden.</p>
          ) : null}
        </div>
      </div>

      <aside className="glass-panel min-h-0 overflow-hidden p-4">
        <header className="mb-3">
          <h2 className="font-display text-xs uppercase tracking-[0.2em] text-jarvis-cyan">Template Status</h2>
          <p className="mt-1 text-[11px] text-white/55">Stub bereit für Home Assistant Adapter.</p>
        </header>

        <div className="grid grid-cols-3 gap-2">
          <article className="rounded-md border border-white/15 bg-white/5 p-2 text-center">
            <span className="text-[10px] text-white/55">Entities</span>
            <strong className="mt-1 block text-sm text-jarvis-cyan">{entities.length}</strong>
          </article>
          <article className="rounded-md border border-white/15 bg-white/5 p-2 text-center">
            <span className="text-[10px] text-white/55">Active</span>
            <strong className="mt-1 block text-sm text-jarvis-cyan">{activeCount}</strong>
          </article>
          <article className="rounded-md border border-white/15 bg-white/5 p-2 text-center">
            <span className="text-[10px] text-white/55">Provider</span>
            <strong className="mt-1 block text-sm text-jarvis-cyan">Stub</strong>
          </article>
        </div>

        <ul className="mt-3 space-y-2 text-sm text-white/70">
          <li>Keine externe Verbindung in v1.</li>
          <li>Service-Calls werden lokal simuliert.</li>
          <li>UI bleibt kompatibel für echten Provider.</li>
        </ul>
      </aside>
    </section>
  );
}
