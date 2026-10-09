import { memo } from "react";
import { Bot, User, Volume2 } from "lucide-react";
import type { ChatMessage } from "../api";

type MessageBubbleProps = {
  message: ChatMessage;
  onSpeak: (content: string) => void;
};

const MessageBubble = memo(function MessageBubble({ message, onSpeak }: MessageBubbleProps) {
  const isAssistant = message.role === "assistant";

  return (
    <article className={`flex ${isAssistant ? "justify-start" : "justify-end"}`}>
      <div className={`flex max-w-[92%] gap-2 ${isAssistant ? "flex-row" : "flex-row-reverse"}`}>
        <div
          className={[
            "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border",
            isAssistant ? "border-jarvis-cyan/45 bg-jarvis-cyan/10 text-jarvis-cyan" : "border-jarvis-blue/45 bg-jarvis-blue/15 text-jarvis-blue"
          ].join(" ")}
        >
          {isAssistant ? <Bot size={15} /> : <User size={15} />}
        </div>

        <div
          className={[
            "rounded-xl border px-3 py-2 text-[12px] leading-relaxed backdrop-blur-sm",
            isAssistant
              ? "border-jarvis-cyan/28 bg-jarvis-cyan/10 shadow-[0_0_15px_rgba(0,242,255,0.12)]"
              : "border-jarvis-blue/30 bg-jarvis-blue/15 text-right shadow-[0_0_15px_rgba(0,102,255,0.12)]"
          ].join(" ")}
        >
          <header className="mb-1 flex items-center justify-between gap-3 text-[10px] text-white/55">
            <span>{isAssistant ? "Jarvis" : "Du"}</span>
            <time>{new Date(message.created_at).toLocaleTimeString()}</time>
          </header>

          <p className="whitespace-pre-wrap text-white/90">{message.content}</p>

          {isAssistant ? (
            <button
              type="button"
              className="mt-2 inline-flex items-center gap-1 rounded-md border border-jarvis-cyan/35 px-2 py-1 text-[10px] text-jarvis-cyan transition hover:bg-jarvis-cyan/15"
              onClick={() => onSpeak(message.content)}
            >
              <Volume2 size={12} /> Vorlesen
            </button>
          ) : null}
        </div>
      </div>
    </article>
  );
});

export default MessageBubble;
