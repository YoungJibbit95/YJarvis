type DiagnosticItem = {
  label: string;
  value: number;
};

type SystemStatusProps = {
  diagnostics: DiagnosticItem[];
};

export default function SystemStatus({ diagnostics }: SystemStatusProps) {
  return (
    <div className="space-y-3">
      {diagnostics.map((item) => (
        <div key={item.label} className="rounded-lg border border-white/10 bg-white/5 p-2">
          <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-white/60">
            <span>{item.label}</span>
            <span>{item.value}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full border border-white/10 bg-black/40">
            <div
              className="h-full rounded-full bg-gradient-to-r from-jarvis-blue to-jarvis-cyan shadow-[0_0_12px_rgba(0,242,255,0.4)]"
              style={{
                width: `${item.value}%`,
                transition: "width 260ms ease-out"
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
