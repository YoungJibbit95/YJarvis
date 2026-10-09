import type { Approval } from "@jarvis/shared-types";

type ApprovalsPanelProps = {
  approvals: Approval[];
  formatJson: (value: Record<string, unknown>) => string;
  onDecision: (id: string, decision: "approve" | "deny") => void;
};

export default function ApprovalsPanel({ approvals, formatJson, onDecision }: ApprovalsPanelProps) {
  return (
    <section className="grid h-full min-h-0 grid-cols-1 gap-4 lg:grid-cols-[1.65fr_0.75fr]">
      <div className="glass-panel min-h-0 overflow-hidden p-4">
        <header className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-sm tracking-wide text-jarvis-cyan">Pending Approvals</h2>
          <span className="text-[10px] text-white/50">Manual Gate</span>
        </header>

        <div className="custom-scrollbar h-full min-h-0 space-y-3 overflow-auto pr-1">
          {!approvals.length ? <p className="text-sm text-white/60">Keine offenen Freigaben.</p> : null}
          {approvals.map((approval) => (
            <article key={approval.id} className="rounded-lg border border-white/10 bg-white/5 p-3">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white/90">{approval.tool_name}</h3>
                <span className="rounded-full border border-jarvis-cyan/35 px-2 py-0.5 text-[10px] uppercase text-jarvis-cyan">
                  {approval.status}
                </span>
              </div>
              <p className="mb-2 text-[11px] text-white/55">Run: {approval.run_id}</p>
              <pre className="custom-scrollbar mb-3 max-h-48 overflow-auto rounded-md border border-white/10 bg-black/40 p-2 text-[11px] text-white/75">
                {formatJson(approval.tool_input)}
              </pre>
              <div className="flex gap-2">
                <button
                  className="rounded-md border border-jarvis-cyan/40 bg-jarvis-cyan/10 px-3 py-1 text-xs text-jarvis-cyan hover:bg-jarvis-cyan/20"
                  onClick={() => onDecision(approval.id, "approve")}
                >
                  Approve
                </button>
                <button
                  className="rounded-md border border-red-400/40 bg-red-500/10 px-3 py-1 text-xs text-red-300 hover:bg-red-500/20"
                  onClick={() => onDecision(approval.id, "deny")}
                >
                  Deny
                </button>
              </div>
            </article>
          ))}
        </div>
      </div>

      <aside className="glass-panel p-4">
        <h3 className="mb-3 font-display text-xs uppercase tracking-[0.2em] text-jarvis-cyan">Policy</h3>
        <ul className="space-y-2 text-sm text-white/70">
          <li>Keine Aktion ohne Zustimmung.</li>
          <li>Datei-Write nur in Allowlist.</li>
          <li>Alle Entscheidungen werden protokolliert.</li>
        </ul>
      </aside>
    </section>
  );
}
