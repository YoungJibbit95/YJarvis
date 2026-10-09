import type { FormEvent, RefObject } from "react";
import { Activity, Mic, Send, Sparkles } from "lucide-react";
import type { ChatMessage } from "../api";
import ArcReactor, { type AssistantMode } from "./ArcReactor";
import DraftBubble, { type DraftMessage } from "./DraftBubble";
import MessageBubble from "./MessageBubble";

type JarvisChatProps = {
  status: string;
  voiceModeEnabled: boolean;
  assistantMode: AssistantMode;
  assistantModeLabel: string;
  orbOpacity: number;
  orbMotionIntensity: number;
  lowMotionMode: boolean;
  busy: boolean;
  sessionId: string;
  visibleMessages: ChatMessage[];
  draftMessages: DraftMessage[];
  input: string;
  composerInputRef: RefObject<HTMLTextAreaElement | null>;
  onInputChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onSpeakMessage: (content: string) => void;
};

export default function JarvisChat({
  status,
  voiceModeEnabled,
  assistantMode,
  assistantModeLabel,
  orbOpacity,
  orbMotionIntensity,
  lowMotionMode,
  busy,
  sessionId,
  visibleMessages,
  draftMessages,
  input,
  composerInputRef,
  onInputChange,
  onSubmit,
  onSpeakMessage
}: JarvisChatProps) {
  const statusBadgeClass =
    assistantMode === "speaking"
      ? "border-jarvis-cyan/55 text-jarvis-cyan"
      : assistantMode === "thinking"
        ? "border-jarvis-blue/50 text-jarvis-blue"
        : "border-white/20 text-white/60";

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={[
            "inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px]",
            voiceModeEnabled ? "border-jarvis-cyan/55 text-jarvis-cyan" : "border-white/20 text-white/60"
          ].join(" ")}
        >
          <Mic size={11} /> Mic {voiceModeEnabled ? "Armed" : "Standby"}
        </span>
        <span className={["inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px]", statusBadgeClass].join(" ")}>
          <Activity size={11} /> Core {assistantModeLabel}
        </span>
        <span
          className={[
            "inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px]",
            busy ? "border-jarvis-cyan/55 text-jarvis-cyan" : "border-white/20 text-white/60"
          ].join(" ")}
        >
          <Sparkles size={11} /> Queue {busy ? "Running" : "Idle"}
        </span>
        <span className="ml-auto truncate text-[10px] text-white/45">Session: {sessionId ? sessionId.slice(0, 8) : "-"}</span>
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-white/10 bg-black/35">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute inset-0 bg-black/45" />
          <div
            className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 scale-[1.18]"
            style={{ opacity: orbOpacity }}
          >
            <ArcReactor mode={assistantMode} variant="backdrop" motionIntensity={orbMotionIntensity} lowMotion={lowMotionMode} />
          </div>
          <div className="absolute inset-y-0 left-0 w-[38%] bg-gradient-to-r from-black/80 to-transparent" />
          <div className="absolute inset-y-0 right-0 w-[38%] bg-gradient-to-l from-black/80 to-transparent" />
          <div className="absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-black/65 to-transparent" />
          <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/70 to-transparent" />
        </div>
        <p className="relative z-10 border-b border-white/10 px-3 py-1.5 text-[10px] text-white/55">{status}</p>
        <div className="relative z-10 custom-scrollbar min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
          {visibleMessages.map((message) => (
            <MessageBubble key={message.id} message={message} onSpeak={onSpeakMessage} />
          ))}
          {draftMessages.map((draft) => (
            <DraftBubble key={draft.runId} draft={draft} />
          ))}
        </div>
      </div>

      <form className="w-full" onSubmit={onSubmit}>
        <div className="w-full rounded-xl border border-white/15 bg-black/45 p-1.5 backdrop-blur">
          <textarea
            ref={composerInputRef}
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            placeholder="Awaiting command..."
            rows={1}
            className="w-full max-h-24 resize-none bg-transparent px-1.5 py-1 text-[11px] leading-5 text-white outline-none placeholder:text-white/35"
          />
          <div className="mt-0.5 flex items-center justify-end px-0.5">
            <button
              type="submit"
              disabled={busy || sessionId.length === 0}
              className="inline-flex items-center gap-1 rounded-full border border-jarvis-cyan/45 bg-jarvis-cyan/10 px-2.5 py-1 text-[10px] font-semibold text-jarvis-cyan transition hover:bg-jarvis-cyan/20 disabled:opacity-40"
            >
              <Send size={12} /> {busy ? "Läuft..." : "Senden"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
