import { memo } from "react";

export type CommandItem = {
  id: string;
  label: string;
  hint: string;
  keywords: string[];
  run: () => void;
};

type CommandPaletteProps = {
  open: boolean;
  query: string;
  items: CommandItem[];
  onQueryChange: (next: string) => void;
  onClose: () => void;
  onRun: (item: CommandItem) => void;
};

const CommandPalette = memo(function CommandPalette({
  open,
  query,
  items,
  onQueryChange,
  onClose,
  onRun
}: CommandPaletteProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="command-palette-overlay" onClick={onClose}>
      <div
        className="command-palette"
        onClick={(event) => {
          event.stopPropagation();
        }}
      >
        <header>
          <h3>Mission Command</h3>
          <p>Cmd/Ctrl + K</p>
        </header>
        <input
          autoFocus
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Suche Aktionen, Navigation, Voice..."
        />
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <button
                className="secondary"
                type="button"
                onClick={() => {
                  onRun(item);
                }}
              >
                <span>{item.label}</span>
                <small>{item.hint}</small>
              </button>
            </li>
          ))}
          {items.length === 0 ? <li className="empty">Keine Treffer.</li> : null}
        </ul>
      </div>
    </div>
  );
});

export default CommandPalette;
