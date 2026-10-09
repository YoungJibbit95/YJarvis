import { memo } from "react";

export type TimelineEntry = {
  id: string;
  runId: string;
  state: string;
  detail?: string;
  timestamp: string;
};

type TimelineRowProps = {
  item: TimelineEntry;
};

const TimelineRow = memo(function TimelineRow({ item }: TimelineRowProps) {
  return (
    <li className="rounded-lg border border-white/10 bg-white/5 p-1.5">
      <div className="mb-1 flex items-center justify-between gap-2 text-[9px] text-white/60">
        <span className="rounded-full border border-jarvis-cyan/35 px-1.5 py-0.5 uppercase tracking-wider text-jarvis-cyan">
          {item.state}
        </span>
        <span>{item.runId.slice(0, 8)}</span>
      </div>
      <p className="text-[11px] text-white/82">{item.detail || "-"}</p>
      <time className="mt-1 block text-[9px] text-white/45">{new Date(item.timestamp).toLocaleTimeString()}</time>
    </li>
  );
});

export default TimelineRow;
