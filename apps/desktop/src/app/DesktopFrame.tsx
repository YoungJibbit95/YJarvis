import type { ReactNode } from "react";
import "./desktop-frame.css";

export function DesktopFrame({ children }: { children: ReactNode }) {
  const controls = window.jarvisDesktop?.windowControls;
  if (!controls) return <>{children}</>;
  return (
    <div className="desktop-frame">
      <header className="desktop-titlebar" onDoubleClick={(event) => {
        if (!(event.target as HTMLElement).closest("button")) controls.toggleMaximize();
      }}>
        <div className="desktop-window-controls" aria-label="Fenstersteuerung">
          <button className="window-close" type="button" aria-label="Fenster schließen" title="Schließen" onClick={controls.close}><span aria-hidden="true">×</span></button>
          <button className="window-minimize" type="button" aria-label="Fenster minimieren" title="Minimieren" onClick={controls.minimize}><span aria-hidden="true">−</span></button>
          <button className="window-maximize" type="button" aria-label="Fenster maximieren oder wiederherstellen" title="Maximieren / Wiederherstellen" onClick={controls.toggleMaximize}><span aria-hidden="true">+</span></button>
        </div>
        <span className="desktop-window-title">YJarvis</span>
      </header>
      <div className="desktop-content">{children}</div>
    </div>
  );
}
