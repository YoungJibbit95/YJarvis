import { memo } from "react";
import { Bot } from "lucide-react";

export type DraftMessage = {
  runId: string;
  content: string;
};

type DraftBubbleProps = {
  draft: DraftMessage;
};

const DraftBubble = memo(function DraftBubble({ draft }: DraftBubbleProps) {
  return (
    <article className="flex justify-start">
      <div className="flex max-w-[92%] gap-2">
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-jarvis-cyan/45 bg-jarvis-cyan/10 text-jarvis-cyan">
          <Bot size={15} />
        </div>
        <div className="rounded-xl border border-dashed border-jarvis-cyan/35 bg-jarvis-cyan/7 px-3 py-2 text-[12px]">
          <header className="mb-1 flex items-center justify-between gap-3 text-[10px] text-white/55">
            <span>Jarvis</span>
            <time>stream</time>
          </header>
          <p className="whitespace-pre-wrap text-white/85">{draft.content || "..."}</p>
        </div>
      </div>
    </article>
  );
});

export default DraftBubble;
