import type { ReactNode } from "react";

type HUDPanelProps = {
  title: string;
  subtitle?: string;
  className?: string;
  delay?: number;
  children: ReactNode;
};

export default function HUDPanel({ title, subtitle, className, delay = 0, children }: HUDPanelProps) {
  return (
    <section
      className={`glass-panel group relative flex min-h-0 flex-col overflow-hidden p-3 ${className || ""}`.trim()}
      style={{
        background:
          "linear-gradient(135deg, rgba(var(--accent-rgb), 0.06) 0%, rgba(0, 0, 0, var(--ui-panel-opacity, 0.62)) 100%)",
        opacity: 1,
        transform: "translateZ(0)",
        transition: `opacity 220ms ease-out ${Math.max(0, delay) * 1000}ms`
      }}
    >
      <div className="pointer-events-none absolute left-0 top-0 z-0 h-px w-full bg-jarvis-cyan/20" />
      <div className="absolute left-0 top-0 h-3 w-3 border-l-2 border-t-2 border-jarvis-cyan/70" />
      <div className="absolute right-0 top-0 h-3 w-3 border-r-2 border-t-2 border-jarvis-cyan/70" />
      <div className="absolute bottom-0 left-0 h-3 w-3 border-b-2 border-l-2 border-jarvis-cyan/70" />
      <div className="absolute bottom-0 right-0 h-3 w-3 border-b-2 border-r-2 border-jarvis-cyan/70" />

      <header className="relative z-10 mb-2 flex items-center justify-between border-b border-white/10 pb-1.5">
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-1.5 rounded-full bg-jarvis-cyan shadow-[0_0_8px_var(--color-jarvis-cyan)]" />
          <h3 className="font-display text-[10px] uppercase tracking-[0.2em] text-jarvis-cyan text-glow">{title}</h3>
        </div>
        <div className="text-right">
          {subtitle ? <small className="block text-[10px] text-white/45">{subtitle}</small> : null}
          <div className="mt-1 flex justify-end gap-1.5">
            <span className="h-1 w-1 rounded-full bg-jarvis-cyan/35" />
            <span className="h-1 w-1 rounded-full bg-jarvis-cyan/35" />
            <span className="h-1 w-3 rounded-full bg-jarvis-cyan/60" />
          </div>
        </div>
      </header>

      <div className="relative z-10 flex min-h-0 flex-1 flex-col font-mono text-sm text-white/85">{children}</div>

      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-jarvis-cyan/[0.02] to-transparent" />
    </section>
  );
}
