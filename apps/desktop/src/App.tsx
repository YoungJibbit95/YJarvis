import {
  FormEvent,
  memo,
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
  useTransition
} from "react";
import type { Approval, JarvisSettings, SmartHomeEntity, StreamEvent } from "@jarvis/shared-types";
import {
  callSmartHomeService,
  createSession,
  decideApproval,
  fetchAudioVoices,
  fetchApprovals,
  fetchMessages,
  fetchSettings,
  fetchSmartHomeEntities,
  saveSettings,
  sendChat,
  speak,
  transcribe,
  waitForBackend,
  wsUrl,
  type ChatMessage
} from "./api";

type TabId = "chat" | "approvals" | "settings" | "smarthome";
type AssistantMode = "idle" | "thinking" | "speaking";

type CommandItem = {
  id: string;
  label: string;
  hint: string;
  keywords: string[];
  run: () => void;
};

type TimelineEntry = {
  id: string;
  runId: string;
  state: string;
  detail?: string;
  timestamp: string;
};

const DEFAULT_SETTINGS: JarvisSettings = {
  model_name: "qwen2.5:3b-instruct",
  language: "de",
  ollama_base_url: "http://127.0.0.1:11434",
  tts_engine: "piper",
  tts_model_path: "",
  tts_voice: "de_DE-thorsten_emotional-medium",
  say_rate_wpm: 235,
  tts_sir_pronunciation: "Sör",
  whisper_model_path: "",
  whisper_binary: "auto",
  allowed_paths: []
};

const SILENCE_TIMEOUT_MS = 1150;
const MIN_SEGMENT_MS = 450;
const MAX_SEGMENT_MS = 16000;
const VOICE_ACTIVITY_THRESHOLD = 0.015;
const VOICE_ACTIVITY_HYSTERESIS = 0.003;
const SILENCE_CONFIRM_FRAMES = 6;
const WS_RECONNECT_BASE_MS = 350;
const WS_RECONNECT_MAX_MS = 5000;
const TTS_INPUT_SUPPRESSION_PREPLAY_MS = 350;
const TTS_INPUT_SUPPRESSION_POSTPLAY_MS = 140;
const RUN_COMPLETION_TIMEOUT_MS = 45_000;
const STREAMING_TTS_MIN_CHARS = 26;
const STREAMING_TTS_SOFT_CHUNK_CHARS = 92;
const WAKE_WORD_ONLY_PATTERNS = [
  "jarvis",
  "hey jarvis",
  "hallo jarvis",
  "ok jarvis",
  "okay jarvis"
];
const TRANSCRIPT_ARTIFACT_PATTERNS = [
  "der assistent erhaelt die erinnerung",
  "assistent erhaelt die erinnerung",
  "erhaelt die erinnerung",
  "erhaelt die erinnerung von jarvis",
  "erhält die erinnerung",
  "erhält die erinnerung von jarvis",
  "swr 2020",
  "ard 2020",
  "zdf 2020"
];
const NORMALIZED_TRANSCRIPT_ARTIFACT_PATTERNS = TRANSCRIPT_ARTIFACT_PATTERNS
  .map((pattern) => normalizeForEchoCheck(pattern))
  .filter(Boolean);
const SHORT_STATION_YEAR_ARTIFACT_REGEX = /^(?:swr|ard|zdf|rtl|orf)\s+\d{2,4}$/i;
const WAKE_WORD_PREFIX_REGEX = /^(?:(?:hey|hallo|ok|okay)\s+)?jarvis\b[\s,.:;\-]*(.*)$/i;
const SPEECH_BOUNDARY_REGEX = /(?:[.!?](?:\s+|$))|(?:[:;](?:\s+|$))|(?:\n+)/g;
const QUICK_ACTIONS: Array<{ label: string; prompt: string }> = [
  {
    label: "Systemstatus",
    prompt: "Jarvis, gib mir den aktuellen Systemstatus."
  },
  {
    label: "Tagesfokus",
    prompt: "Jarvis, gib mir einen kurzen Arbeitsfokus fuer die naechsten 2 Stunden."
  },
  {
    label: "Reminder",
    prompt: "Jarvis, mach mir eine Erinnerung auf morgen 10 Uhr die sagt Licht ausmachen."
  },
  {
    label: "Kalender",
    prompt: "Jarvis, plane morgen um 10 Uhr einen Termin mit dem Titel Projekt-Review fuer 30 Minuten."
  }
];

function formatJson(value: Record<string, unknown>) {
  return JSON.stringify(value, null, 2);
}

function uniqueMessageId() {
  return Date.now() + Math.floor(Math.random() * 1000);
}

function pickRecorderMimeType(): string | undefined {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  for (const candidate of candidates) {
    if (MediaRecorder.isTypeSupported(candidate)) {
      return candidate;
    }
  }
  return undefined;
}

function normalizeForEchoCheck(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isLikelyEchoTranscript(transcript: string, spokenAssistantText: string): boolean {
  const normalizedTranscript = normalizeForEchoCheck(transcript);
  const normalizedAssistant = normalizeForEchoCheck(spokenAssistantText);

  if (!normalizedTranscript || !normalizedAssistant) {
    return false;
  }

  if (normalizedTranscript.length < 12 || normalizedAssistant.length < 12) {
    return false;
  }

  if (normalizedAssistant.includes(normalizedTranscript)) {
    return true;
  }

  const shortAssistantSlice = normalizedAssistant.slice(0, Math.min(72, normalizedAssistant.length));
  if (shortAssistantSlice.length >= 12 && normalizedTranscript.includes(shortAssistantSlice)) {
    return true;
  }

  return false;
}

function shouldIgnoreTranscriptArtifact(text: string): boolean {
  const normalized = normalizeForEchoCheck(text);
  if (!normalized) {
    return false;
  }

  if (WAKE_WORD_ONLY_PATTERNS.includes(normalized)) {
    return true;
  }

  if (SHORT_STATION_YEAR_ARTIFACT_REGEX.test(normalized)) {
    return true;
  }

  return NORMALIZED_TRANSCRIPT_ARTIFACT_PATTERNS.some((pattern) => normalized.includes(pattern));
}

function shortModelName(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) {
    return "-";
  }
  return trimmed.length > 22 ? `${trimmed.slice(0, 22)}...` : trimmed;
}

function fileNameFromPath(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "auto";
  }
  const normalized = trimmed.replace(/\\/g, "/");
  const parts = normalized.split("/");
  return parts[parts.length - 1] || trimmed;
}

function extractWakeWordCommand(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed) {
    return null;
  }

  const match = trimmed.match(WAKE_WORD_PREFIX_REGEX);
  if (!match) {
    return null;
  }

  return (match[1] || "").trim();
}

function normalizeSpeechChunk(text: string): string {
  return text
    .replace(/\s+/g, " ")
    .replace(/^[,;:\-]+/, "")
    .trim();
}

function splitReadySpeechChunk(
  source: string,
  {
    flushTail
  }: {
    flushTail: boolean;
  }
): { chunk: string; consumed: number } {
  if (!source.trim()) {
    return { chunk: "", consumed: 0 };
  }

  let cutoff = -1;
  const boundaries = new RegExp(SPEECH_BOUNDARY_REGEX);
  let match: RegExpExecArray | null = boundaries.exec(source);
  while (match) {
    cutoff = match.index + match[0].length;
    match = boundaries.exec(source);
  }

  if (cutoff <= 0 && source.length >= STREAMING_TTS_SOFT_CHUNK_CHARS) {
    const softBreak = source.lastIndexOf(" ", STREAMING_TTS_SOFT_CHUNK_CHARS);
    if (softBreak > STREAMING_TTS_MIN_CHARS) {
      cutoff = softBreak + 1;
    }
  }

  if (cutoff <= 0 && flushTail) {
    cutoff = source.length;
  }

  if (cutoff <= 0) {
    return { chunk: "", consumed: 0 };
  }

  const chunk = normalizeSpeechChunk(source.slice(0, cutoff));
  if (!chunk) {
    return { chunk: "", consumed: cutoff };
  }

  if (!flushTail && chunk.length < STREAMING_TTS_MIN_CHARS) {
    return { chunk: "", consumed: 0 };
  }

  return { chunk, consumed: cutoff };
}

type DraftMessage = {
  runId: string;
  content: string;
};

const MessageBubble = memo(function MessageBubble({
  message,
  onSpeak
}: {
  message: ChatMessage;
  onSpeak: (content: string) => void;
}) {
  return (
    <article className={`message ${message.role}`}>
      <header>
        <span className="role-tag">{message.role === "assistant" ? "Jarvis" : "Du"}</span>
        <time>{new Date(message.created_at).toLocaleTimeString()}</time>
      </header>
      <p>{message.content}</p>
      {message.role === "assistant" ? (
        <button
          className="tiny"
          onClick={() => {
            onSpeak(message.content);
          }}
        >
          Vorlesen
        </button>
      ) : null}
    </article>
  );
});

const DraftBubble = memo(function DraftBubble({ draft }: { draft: DraftMessage }) {
  return (
    <article className="message assistant draft">
      <header>
        <span className="role-tag">Jarvis</span>
        <time>stream</time>
      </header>
      <p>{draft.content || "..."}</p>
    </article>
  );
});

const TimelineRow = memo(function TimelineRow({ item }: { item: TimelineEntry }) {
  return (
    <li>
      <div>
        <strong className={`state-badge state-${item.state}`}>{item.state}</strong>
        <span>{item.runId.slice(0, 8)}</span>
      </div>
      <p>{item.detail || "-"}</p>
      <time>{new Date(item.timestamp).toLocaleTimeString()}</time>
    </li>
  );
});

const CommandPalette = memo(function CommandPalette({
  open,
  query,
  items,
  onQueryChange,
  onClose,
  onRun
}: {
  open: boolean;
  query: string;
  items: CommandItem[];
  onQueryChange: (next: string) => void;
  onClose: () => void;
  onRun: (item: CommandItem) => void;
}) {
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

function App() {
  const [activeTab, setActiveTab] = useState<TabId>("chat");
  const [sessionId, setSessionId] = useState<string>("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [draftByRun, setDraftByRun] = useState<Record<string, string>>({});
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Starte lokale Session...");

  const [approvals, setApprovals] = useState<Approval[]>([]);

  const [settings, setSettings] = useState<JarvisSettings>(DEFAULT_SETTINGS);
  const [settingsDraft, setSettingsDraft] = useState<JarvisSettings>(DEFAULT_SETTINGS);
  const [allowlistInput, setAllowlistInput] = useState("");
  const [sayVoices, setSayVoices] = useState<string[]>([]);

  const [entities, setEntities] = useState<SmartHomeEntity[]>([]);

  const [voiceModeEnabled, setVoiceModeEnabled] = useState(false);
  const [voiceRepliesEnabled, setVoiceRepliesEnabled] = useState(true);
  const [assistantMode, setAssistantMode] = useState<AssistantMode>("idle");
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const [isTabPending, startTabTransition] = useTransition();

  const busyRef = useRef(false);
  const voiceRepliesEnabledRef = useRef(true);
  const ttsPlaybackActiveRef = useRef(false);
  const suppressVoiceInputUntilRef = useRef(0);
  const lastAssistantSpokenTextRef = useRef("");

  const voiceQueueRef = useRef<string[]>([]);
  const voiceFlushRunningRef = useRef(false);
  const ttsQueueRef = useRef<string[]>([]);
  const ttsQueueRunningRef = useRef(false);
  const spokenOffsetByRunRef = useRef<Record<string, number>>({});
  const thinkingRunsRef = useRef<Set<string>>(new Set());

  const voiceModeEnabledRef = useRef(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mediaChunksRef = useRef<Blob[]>([]);

  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const analyserDataRef = useRef<Uint8Array | null>(null);
  const monitorRafRef = useRef<number | null>(null);
  const composerInputRef = useRef<HTMLTextAreaElement | null>(null);

  const segmentStartAtRef = useRef(0);
  const lastSpeechAtRef = useRef(0);
  const speechDetectedInSegmentRef = useRef(false);
  const silenceFrameCountRef = useRef(0);
  const voiceGateOpenRef = useRef(false);
  const busyWatchdogTimerRef = useRef<number | null>(null);
  const tokenBufferByRunRef = useRef<Record<string, string>>({});
  const tokenFlushTimerRef = useRef<number | null>(null);

  const sortedMessages = useMemo(() => {
    return [...messages].sort((a, b) => a.id - b.id);
  }, [messages]);

  const deferredTimeline = useDeferredValue(timeline);
  const deferredDraftByRun = useDeferredValue(draftByRun);
  const draftMessages = useMemo(() => {
    return Object.entries(deferredDraftByRun).map(([runId, content]) => ({ runId, content }));
  }, [deferredDraftByRun]);

  function clearTokenFlushTimer() {
    if (tokenFlushTimerRef.current !== null) {
      window.clearTimeout(tokenFlushTimerRef.current);
      tokenFlushTimerRef.current = null;
    }
  }

  function flushBufferedTokens() {
    clearTokenFlushTimer();

    const bufferedTokens = tokenBufferByRunRef.current;
    const entries = Object.entries(bufferedTokens).filter(([, chunk]) => chunk.length > 0);
    tokenBufferByRunRef.current = {};
    if (!entries.length) {
      return;
    }

    setDraftByRun((previous) => {
      const next = { ...previous };
      let changed = false;
      for (const [runId, chunk] of entries) {
        const nextDraft = `${next[runId] || ""}${chunk}`;
        next[runId] = nextDraft;
        enqueueStreamingSpeechForRun(runId, nextDraft, { flushTail: false });
        changed = true;
      }
      return changed ? next : previous;
    });
  }

  function enqueueBufferedToken(runId: string, token: string) {
    if (!token) {
      return;
    }

    tokenBufferByRunRef.current[runId] = `${tokenBufferByRunRef.current[runId] || ""}${token}`;
    if (tokenFlushTimerRef.current !== null) {
      return;
    }

    tokenFlushTimerRef.current = window.setTimeout(() => {
      flushBufferedTokens();
    }, 32);
  }

  function syncAssistantMode() {
    if (ttsPlaybackActiveRef.current || ttsQueueRunningRef.current || ttsQueueRef.current.length > 0) {
      setAssistantMode("speaking");
      return;
    }

    if (thinkingRunsRef.current.size > 0 || busyRef.current) {
      setAssistantMode("thinking");
      return;
    }

    setAssistantMode("idle");
  }

  function updateThinkingStateForRun(runId: string, state: string) {
    if (state === "done" || state === "error") {
      thinkingRunsRef.current.delete(runId);
    } else if (state === "received" || state === "thinking" || state === "executing" || state === "approval_required") {
      thinkingRunsRef.current.add(runId);
    }
    syncAssistantMode();
  }

  async function flushTtsQueue() {
    if (ttsQueueRunningRef.current) {
      return;
    }

    if (!voiceRepliesEnabledRef.current) {
      ttsQueueRef.current = [];
      syncAssistantMode();
      return;
    }

    const nextChunk = ttsQueueRef.current.shift();
    if (!nextChunk) {
      syncAssistantMode();
      return;
    }

    ttsQueueRunningRef.current = true;
    ttsPlaybackActiveRef.current = true;
    syncAssistantMode();
    suppressVoiceInputFor(TTS_INPUT_SUPPRESSION_PREPLAY_MS);

    if (voiceModeEnabledRef.current && mediaRecorderRef.current?.state === "recording") {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
    }

    try {
      lastAssistantSpokenTextRef.current = nextChunk;
      await speak(nextChunk);
    } catch (error) {
      setStatus((error as Error).message);
    } finally {
      ttsPlaybackActiveRef.current = false;
      ttsQueueRunningRef.current = false;
      suppressVoiceInputFor(TTS_INPUT_SUPPRESSION_POSTPLAY_MS);
      resumeRecorderAfterSuppression();
      syncAssistantMode();
    }

    if (ttsQueueRef.current.length > 0) {
      window.setTimeout(() => {
        void flushTtsQueue();
      }, 18);
    }
  }

  function enqueueSpeechChunk(
    text: string,
    {
      manual,
      interrupt
    }: {
      manual?: boolean;
      interrupt?: boolean;
    } = {}
  ) {
    const chunk = normalizeSpeechChunk(text);
    if (!chunk) {
      return;
    }

    if (!manual && !voiceRepliesEnabledRef.current) {
      return;
    }

    if (interrupt) {
      ttsQueueRef.current = [chunk];
    } else {
      ttsQueueRef.current.push(chunk);
    }

    syncAssistantMode();
    void flushTtsQueue();
  }

  function enqueueStreamingSpeechForRun(
    runId: string,
    fullText: string,
    {
      flushTail
    }: {
      flushTail: boolean;
    }
  ) {
    if (!voiceRepliesEnabledRef.current) {
      return;
    }

    const safeText = fullText || "";
    let offset = spokenOffsetByRunRef.current[runId] || 0;
    if (offset < 0 || offset > safeText.length) {
      offset = 0;
    }

    let remaining = safeText.slice(offset);
    let consumedTotal = 0;
    while (remaining) {
      const { chunk, consumed } = splitReadySpeechChunk(remaining, { flushTail });
      if (consumed <= 0) {
        break;
      }
      consumedTotal += consumed;
      if (chunk) {
        enqueueSpeechChunk(chunk);
      }
      remaining = remaining.slice(consumed);
      if (!flushTail) {
        break;
      }
    }

    if (consumedTotal > 0) {
      spokenOffsetByRunRef.current[runId] = offset + consumedTotal;
    }
  }

  function clearStreamingSpeechForRun(runId: string) {
    delete spokenOffsetByRunRef.current[runId];
  }

  function isVoiceInputSuppressed(): boolean {
    return ttsPlaybackActiveRef.current || Date.now() < suppressVoiceInputUntilRef.current;
  }

  function suppressVoiceInputFor(durationMs: number) {
    if (durationMs <= 0) {
      return;
    }

    const candidate = Date.now() + durationMs;
    if (candidate > suppressVoiceInputUntilRef.current) {
      suppressVoiceInputUntilRef.current = candidate;
    }
  }

  function resumeRecorderAfterSuppression() {
    if (!voiceModeEnabledRef.current) {
      return;
    }

    const waitMs = Math.max(0, suppressVoiceInputUntilRef.current - Date.now()) + 80;
    window.setTimeout(() => {
      if (!voiceModeEnabledRef.current) {
        return;
      }
      if (isVoiceInputSuppressed()) {
        resumeRecorderAfterSuppression();
        return;
      }
      if (mediaStreamRef.current && !mediaRecorderRef.current) {
        startRecorderSegment();
      }
    }, waitMs);
  }

  function clearBusyWatchdog() {
    if (busyWatchdogTimerRef.current !== null) {
      window.clearTimeout(busyWatchdogTimerRef.current);
      busyWatchdogTimerRef.current = null;
    }
  }

  function releaseBusyLock() {
    clearBusyWatchdog();
    busyRef.current = false;
    setBusy(false);
    syncAssistantMode();
  }

  function armBusyWatchdog() {
    clearBusyWatchdog();
    busyWatchdogTimerRef.current = window.setTimeout(() => {
      releaseBusyLock();
      setStatus("Antwort-Timeout erreicht, Sprachqueue wird fortgesetzt.");
    }, RUN_COMPLETION_TIMEOUT_MS);
  }

  async function refreshApprovals() {
    const pending = await fetchApprovals();
    setApprovals(pending);
  }

  async function refreshSmartHome() {
    const items = await fetchSmartHomeEntities();
    setEntities(items);
  }

  async function refreshAudioVoices() {
    const voices = await fetchAudioVoices();
    setSayVoices(voices);
  }

  function shutdownAudioNodes() {
    if (monitorRafRef.current !== null) {
      cancelAnimationFrame(monitorRafRef.current);
      monitorRafRef.current = null;
    }

    analyserRef.current = null;
    analyserDataRef.current = null;

    if (sourceNodeRef.current) {
      try {
        sourceNodeRef.current.disconnect();
      } catch {
        // ignore
      }
      sourceNodeRef.current = null;
    }

    if (audioContextRef.current) {
      const context = audioContextRef.current;
      audioContextRef.current = null;
      void context.close().catch(() => {
        // ignore
      });
    }
  }

  function stopVoiceModeInternal({ updateStatus }: { updateStatus: boolean }) {
    voiceModeEnabledRef.current = false;
    setVoiceModeEnabled(false);

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
    }

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }

    shutdownAudioNodes();

    if (updateStatus) {
      setStatus("Sprachmodus aus.");
    }
  }

  async function submitMessage(message: string, source: "text" | "voice"): Promise<boolean> {
    const trimmed = message.trim();
    if (!trimmed || !sessionId || busyRef.current) {
      return false;
    }

    busyRef.current = true;
    setBusy(true);
    syncAssistantMode();

    if (source === "text") {
      setInput("");
    }

    setMessages((previous) => [
      ...previous,
      {
        id: uniqueMessageId(),
        role: "user",
        content: trimmed,
        created_at: new Date().toISOString()
      }
    ]);

    try {
      await sendChat(sessionId, trimmed);
      armBusyWatchdog();
      return true;
    } catch (error) {
      releaseBusyLock();
      setStatus((error as Error).message);
      return false;
    }
  }

  async function flushVoiceQueue() {
    if (voiceFlushRunningRef.current || busyRef.current || !sessionId) {
      return;
    }

    const nextMessage = voiceQueueRef.current.shift();
    if (!nextMessage) {
      return;
    }

    voiceFlushRunningRef.current = true;
    try {
      const sent = await submitMessage(nextMessage, "voice");
      if (!sent) {
        voiceQueueRef.current.unshift(nextMessage);
      }
    } finally {
      voiceFlushRunningRef.current = false;
    }

    if (!busyRef.current && voiceQueueRef.current.length > 0) {
      window.setTimeout(() => {
        void flushVoiceQueue();
      }, 80);
    }
  }

  function enqueueVoiceMessage(message: string) {
    const trimmed = message.trim();
    if (!trimmed) {
      return;
    }

    voiceQueueRef.current.push(trimmed);
    void flushVoiceQueue();
  }

  async function handleRecordedSegment(blob: Blob) {
    if (blob.size === 0) {
      return;
    }

    try {
      setStatus("Transkribiere Audio lokal...");
      const result = await transcribe(blob);
      const text = result.text.trim();
      if (!text) {
        setStatus("Keine Sprache erkannt.");
        return;
      }

      if (isVoiceInputSuppressed()) {
        setStatus("Audioeingabe waehrend eigener Sprachausgabe ignoriert.");
        return;
      }

      if (isLikelyEchoTranscript(text, lastAssistantSpokenTextRef.current)) {
        setStatus("Eigenes Lautsprecher-Echo erkannt und ignoriert.");
        return;
      }

      if (shouldIgnoreTranscriptArtifact(text)) {
        const normalized = normalizeForEchoCheck(text);
        if (WAKE_WORD_ONLY_PATTERNS.includes(normalized)) {
          setStatus("Wakeword erkannt. Bitte direkt danach den Auftrag sprechen.");
        } else {
          setStatus("Unsichere STT-Ausgabe erkannt und verworfen.");
        }
        return;
      }

      const wakeCommand = extractWakeWordCommand(text);
      if (wakeCommand === null) {
        setStatus("Ignoriert: Bitte mit `Jarvis ...` am Satzanfang sprechen.");
        return;
      }

      if (!wakeCommand) {
        setStatus("Wakeword erkannt. Bitte direkt danach den Auftrag sprechen.");
        return;
      }

      setStatus(`Erkannt (${result.latency_ms} ms): ${wakeCommand}`);
      enqueueVoiceMessage(wakeCommand);
    } catch (error) {
      setStatus((error as Error).message);
    }
  }

  async function speakWithEchoGuard(
    text: string,
    {
      manual,
      interrupt
    }: {
      manual?: boolean;
      interrupt?: boolean;
    } = {}
  ) {
    enqueueSpeechChunk(text, { manual, interrupt });
  }

  function startRecorderSegment() {
    const stream = mediaStreamRef.current;
    if (!stream || !voiceModeEnabledRef.current || isVoiceInputSuppressed()) {
      return;
    }

    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      return;
    }

    const mimeType = pickRecorderMimeType();
    const recorderOptions: MediaRecorderOptions = {
      audioBitsPerSecond: 128_000
    };
    if (mimeType) {
      recorderOptions.mimeType = mimeType;
    }
    const recorder = new MediaRecorder(stream, recorderOptions);

    mediaChunksRef.current = [];
    segmentStartAtRef.current = Date.now();
    lastSpeechAtRef.current = Date.now();
    speechDetectedInSegmentRef.current = false;
    silenceFrameCountRef.current = 0;
    voiceGateOpenRef.current = false;

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        mediaChunksRef.current.push(event.data);
      }
    };

    recorder.onstop = () => {
      const blob = new Blob(mediaChunksRef.current, {
        type: recorder.mimeType || "audio/webm"
      });
      mediaChunksRef.current = [];
      mediaRecorderRef.current = null;

      const hadSpeech = speechDetectedInSegmentRef.current;
      if (hadSpeech && !isVoiceInputSuppressed()) {
        void handleRecordedSegment(blob);
      }

      if (voiceModeEnabledRef.current && mediaStreamRef.current) {
        resumeRecorderAfterSuppression();
      }
    };

    recorder.start();
    mediaRecorderRef.current = recorder;
  }

  function startVoiceMonitor() {
    if (!analyserRef.current || !analyserDataRef.current) {
      return;
    }

    const loop = () => {
      if (!voiceModeEnabledRef.current) {
        return;
      }

      const analyser = analyserRef.current;
      const data = analyserDataRef.current;
      const recorder = mediaRecorderRef.current;

      if (!analyser || !data || !recorder || recorder.state !== "recording") {
        monitorRafRef.current = requestAnimationFrame(loop);
        return;
      }

      analyser.getByteTimeDomainData(data);

      let sumSquares = 0;
      for (let i = 0; i < data.length; i += 1) {
        const normalized = (data[i] - 128) / 128;
        sumSquares += normalized * normalized;
      }

      const rms = Math.sqrt(sumSquares / data.length);
      const now = Date.now();

      const openThreshold = VOICE_ACTIVITY_THRESHOLD;
      const closeThreshold = Math.max(0.001, VOICE_ACTIVITY_THRESHOLD - VOICE_ACTIVITY_HYSTERESIS);
      const hasVoiceFrame = voiceGateOpenRef.current ? rms >= closeThreshold : rms >= openThreshold;

      if (hasVoiceFrame) {
        voiceGateOpenRef.current = true;
        speechDetectedInSegmentRef.current = true;
        lastSpeechAtRef.current = now;
        silenceFrameCountRef.current = 0;
      } else {
        voiceGateOpenRef.current = false;
        if (speechDetectedInSegmentRef.current) {
          silenceFrameCountRef.current += 1;
        }
      }

      const elapsed = now - segmentStartAtRef.current;
      const silenceElapsed = now - lastSpeechAtRef.current;

      const shouldCutBySilence =
        speechDetectedInSegmentRef.current &&
        silenceElapsed >= SILENCE_TIMEOUT_MS &&
        silenceFrameCountRef.current >= SILENCE_CONFIRM_FRAMES &&
        elapsed >= MIN_SEGMENT_MS;

      const shouldCutByMaxLength = elapsed >= MAX_SEGMENT_MS;

      if (shouldCutBySilence || shouldCutByMaxLength) {
        try {
          recorder.stop();
        } catch {
          // ignore
        }
      }

      monitorRafRef.current = requestAnimationFrame(loop);
    };

    monitorRafRef.current = requestAnimationFrame(loop);
  }

  async function startVoiceMode() {
    if (voiceModeEnabledRef.current) {
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 48000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      const browserWindow = window as Window & { webkitAudioContext?: typeof AudioContext };
      const AudioContextCtor = browserWindow.AudioContext || browserWindow.webkitAudioContext;
      if (!AudioContextCtor) {
        throw new Error("AudioContext wird in diesem Browser nicht unterstuetzt.");
      }

      const context = new AudioContextCtor();
      const source = context.createMediaStreamSource(stream);
      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);

      audioContextRef.current = context;
      sourceNodeRef.current = source;
      analyserRef.current = analyser;
      analyserDataRef.current = new Uint8Array(analyser.fftSize);

      mediaStreamRef.current = stream;
      voiceModeEnabledRef.current = true;
      setVoiceModeEnabled(true);

      startRecorderSegment();
      startVoiceMonitor();
      setStatus("Sprachmodus aktiv: Sprechen und kurz pausieren zum automatischen Senden.");
    } catch (error) {
      stopVoiceModeInternal({ updateStatus: false });
      setStatus((error as Error).message);
    }
  }

  function stopVoiceMode() {
    stopVoiceModeInternal({ updateStatus: true });
  }

  async function runQuickAction(prompt: string) {
    const trimmed = prompt.trim();
    if (!trimmed) {
      return;
    }

    if (!sessionId || busyRef.current) {
      setInput(trimmed);
      composerInputRef.current?.focus();
      setStatus("Quick Action in Eingabe uebernommen.");
      return;
    }

    await submitMessage(trimmed, "text");
  }

  const switchTab = useCallback(
    (tab: TabId) => {
      startTabTransition(() => {
        setActiveTab(tab);
      });
    },
    [startTabTransition]
  );

  const handleSpeakMessage = useCallback((content: string) => {
    void speakWithEchoGuard(content, { manual: true, interrupt: true }).catch((error) => {
      setStatus((error as Error).message);
    });
  }, []);

  const commandItems = useMemo<CommandItem[]>(() => {
    const quickActionItems = QUICK_ACTIONS.map((action, index) => ({
      id: `quick-${index}`,
      label: action.label,
      hint: action.prompt,
      keywords: ["quick", "prompt", action.label.toLowerCase(), ...action.prompt.toLowerCase().split(" ")],
      run: () => {
        void runQuickAction(action.prompt);
      }
    }));

    return [
      ...quickActionItems,
      {
        id: "nav-chat",
        label: "Go: Chat",
        hint: "Zur Chat-Ansicht wechseln",
        keywords: ["nav", "chat", "konversation"],
        run: () => switchTab("chat")
      },
      {
        id: "nav-approvals",
        label: "Go: Approvals",
        hint: "Offene Freigaben anzeigen",
        keywords: ["nav", "approvals", "freigaben"],
        run: () => switchTab("approvals")
      },
      {
        id: "nav-settings",
        label: "Go: Settings",
        hint: "Agent-Konfiguration öffnen",
        keywords: ["nav", "settings", "config", "einstellungen"],
        run: () => switchTab("settings")
      },
      {
        id: "nav-smarthome",
        label: "Go: Smart Home",
        hint: "Smart-Home Template öffnen",
        keywords: ["nav", "smarthome", "template"],
        run: () => switchTab("smarthome")
      },
      {
        id: "toggle-voice-input",
        label: voiceModeEnabled ? "Voice Input: Stop" : "Voice Input: Start",
        hint: voiceModeEnabled ? "Sprachmodus deaktivieren" : "Sprachmodus aktivieren",
        keywords: ["voice", "mic", "input", voiceModeEnabled ? "stop" : "start"],
        run: () => {
          if (voiceModeEnabled) {
            stopVoiceMode();
          } else {
            void startVoiceMode();
          }
        }
      },
      {
        id: "toggle-voice-replies",
        label: voiceRepliesEnabled ? "Replies: Text only" : "Replies: Voice + Text",
        hint: "Antwortmodus umschalten",
        keywords: ["voice", "reply", "tts", "toggle", "text only"],
        run: () => setVoiceRepliesEnabled((previous) => !previous)
      }
    ];
  }, [voiceModeEnabled, voiceRepliesEnabled, switchTab, sessionId, busy]);

  const filteredCommandItems = useMemo(() => {
    const query = commandQuery.trim().toLowerCase();
    if (!query) {
      return commandItems.slice(0, 10);
    }

    return commandItems
      .filter((item) => {
        const searchBlob = [item.label, item.hint, ...item.keywords].join(" ").toLowerCase();
        return searchBlob.includes(query);
      })
      .slice(0, 10);
  }, [commandItems, commandQuery]);

  const runCommandItem = useCallback((item: CommandItem) => {
    item.run();
    setCommandPaletteOpen(false);
    setCommandQuery("");
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const isCommandK = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
      if (isCommandK) {
        event.preventDefault();
        setCommandPaletteOpen((previous) => !previous);
        return;
      }

      if (event.key === "Escape") {
        setCommandPaletteOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  useEffect(() => {
    busyRef.current = busy;
    syncAssistantMode();
  }, [busy]);

  useEffect(() => {
    voiceRepliesEnabledRef.current = voiceRepliesEnabled;
    if (!voiceRepliesEnabled) {
      ttsQueueRef.current = [];
      spokenOffsetByRunRef.current = {};
      syncAssistantMode();
    }
  }, [voiceRepliesEnabled]);

  useEffect(() => {
    if (!busy) {
      void flushVoiceQueue();
    }
  }, [busy, sessionId]);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        setStatus("Warte auf lokalen Agent...");
        await waitForBackend(45_000);
        if (cancelled) {
          return;
        }

        setStatus("Agent erreichbar, erstelle Session...");
        const session = await createSession();
        if (cancelled) {
          return;
        }

        setSessionId(session.session_id);
        setStatus(`Session aktiv: ${session.session_id}`);

        const [initialMessages, initialApprovals, initialSettings, initialEntities] = await Promise.all([
          fetchMessages(session.session_id),
          fetchApprovals(),
          fetchSettings(),
          fetchSmartHomeEntities()
        ]);

        if (cancelled) {
          return;
        }

        setMessages(initialMessages);
        setApprovals(initialApprovals);
        setSettings(initialSettings);
        setSettingsDraft(initialSettings);
        setEntities(initialEntities);
        refreshAudioVoices().catch((error) => setStatus((error as Error).message));
      } catch (error) {
        if (!cancelled) {
          setStatus((error as Error).message);
        }
      }
    }

    bootstrap();

    return () => {
      cancelled = true;
      clearBusyWatchdog();
      clearTokenFlushTimer();
      tokenBufferByRunRef.current = {};
      stopVoiceModeInternal({ updateStatus: false });
      ttsQueueRef.current = [];
      spokenOffsetByRunRef.current = {};
      thinkingRunsRef.current.clear();
      syncAssistantMode();
    };
  }, []);

  useEffect(() => {
    if (settingsDraft.tts_engine.trim().toLowerCase() !== "say") {
      return;
    }
    if (sayVoices.length > 0) {
      return;
    }
    refreshAudioVoices().catch((error) => setStatus((error as Error).message));
  }, [settingsDraft.tts_engine, sayVoices.length]);

  useEffect(() => {
    if (!sessionId) {
      return;
    }

    let cancelled = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let reconnectAttempt = 0;

    const clearReconnectTimer = () => {
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    const scheduleReconnect = () => {
      if (cancelled) {
        return;
      }
      clearReconnectTimer();

      const delay = Math.min(
        WS_RECONNECT_MAX_MS,
        WS_RECONNECT_BASE_MS * Math.pow(2, reconnectAttempt)
      );
      reconnectAttempt += 1;
      setStatus(`WebSocket getrennt. Verbinde erneut in ${Math.max(1, Math.round(delay / 1000))}s...`);

      reconnectTimer = window.setTimeout(() => {
        connectSocket();
      }, delay);
    };

    const connectSocket = () => {
      if (cancelled) {
        return;
      }

      clearReconnectTimer();
      const nextSocket = new WebSocket(wsUrl(sessionId));
      socket = nextSocket;

      nextSocket.onopen = () => {
        reconnectAttempt = 0;
        setStatus(`Verbunden mit Agent (${sessionId})`);
      };

      nextSocket.onmessage = (event) => {
        const payload = JSON.parse(event.data) as StreamEvent;

        if (payload.event === "token") {
          enqueueBufferedToken(payload.run_id, payload.token);
          return;
        }

        if (payload.event === "message") {
          flushBufferedTokens();
          setDraftByRun((previous) => {
            const next = { ...previous };
            delete next[payload.run_id];
            return next;
          });

          setMessages((previous) => [
            ...previous,
            {
              id: uniqueMessageId(),
              role: payload.role,
              content: payload.content,
              created_at: payload.timestamp
            }
          ]);

          if (payload.role === "assistant") {
            releaseBusyLock();
            if (voiceRepliesEnabledRef.current) {
              enqueueStreamingSpeechForRun(payload.run_id, payload.content, { flushTail: true });
            }
          }
          clearStreamingSpeechForRun(payload.run_id);
          return;
        }

        if (payload.event === "run_state") {
          flushBufferedTokens();
          updateThinkingStateForRun(payload.run_id, payload.state);
          setTimeline((previous) => [
            {
              id: `${payload.run_id}-${payload.timestamp}`,
              runId: payload.run_id,
              state: payload.state,
              detail: payload.detail,
              timestamp: payload.timestamp
            },
            ...previous
          ].slice(0, 120));

          if (payload.state === "approval_required") {
            refreshApprovals().catch((error) => setStatus((error as Error).message));
          }

          if (payload.state === "done" || payload.state === "error") {
            releaseBusyLock();
            clearStreamingSpeechForRun(payload.run_id);
            refreshApprovals().catch((error) => setStatus((error as Error).message));
          }
        }
      };

      nextSocket.onerror = () => {
        try {
          nextSocket.close();
        } catch {
          // ignore
        }
      };

      nextSocket.onclose = () => {
        if (cancelled) {
          return;
        }
        clearTokenFlushTimer();
        tokenBufferByRunRef.current = {};
        thinkingRunsRef.current.clear();
        spokenOffsetByRunRef.current = {};
        syncAssistantMode();
        if (busyRef.current) {
          releaseBusyLock();
        }
        scheduleReconnect();
      };
    };

    connectSocket();

    return () => {
      cancelled = true;
      clearReconnectTimer();
      clearBusyWatchdog();
      clearTokenFlushTimer();
      tokenBufferByRunRef.current = {};
      thinkingRunsRef.current.clear();
      spokenOffsetByRunRef.current = {};
      syncAssistantMode();
      if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
        socket.close();
      }
    };
  }, [sessionId]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitMessage(input, "text");
  }

  async function handleApproval(id: string, decision: "approve" | "deny") {
    try {
      await decideApproval(id, decision);
      await refreshApprovals();
    } catch (error) {
      setStatus((error as Error).message);
    }
  }

  async function handleSaveSettings() {
    try {
      const uniquePaths = Array.from(new Set(settingsDraft.allowed_paths.map((path) => path.trim()).filter(Boolean)));
      const normalizedSayRate = Math.min(420, Math.max(80, Math.round(settingsDraft.say_rate_wpm || 235)));
      const normalizedSirPronunciation = settingsDraft.tts_sir_pronunciation.trim() || "Sör";
      const payload = {
        ...settingsDraft,
        say_rate_wpm: normalizedSayRate,
        tts_sir_pronunciation: normalizedSirPronunciation,
        allowed_paths: uniquePaths
      };
      const saved = await saveSettings(payload);
      setSettings(saved);
      setSettingsDraft(saved);
      setStatus("Settings gespeichert.");
    } catch (error) {
      setStatus((error as Error).message);
    }
  }

  function addAllowlistPath() {
    const trimmed = allowlistInput.trim();
    if (!trimmed) {
      return;
    }
    setSettingsDraft((previous) => ({
      ...previous,
      allowed_paths: [...previous.allowed_paths, trimmed]
    }));
    setAllowlistInput("");
  }

  function removeAllowlistPath(path: string) {
    setSettingsDraft((previous) => ({
      ...previous,
      allowed_paths: previous.allowed_paths.filter((candidate) => candidate !== path)
    }));
  }

  async function handleSmartHomeAction(entityId: string, service: string) {
    try {
      await callSmartHomeService(entityId, service);
      await refreshSmartHome();
    } catch (error) {
      setStatus((error as Error).message);
    }
  }

  function renderChatTab() {
    const assistantModeLabel =
      assistantMode === "speaking" ? "Speaking" : assistantMode === "thinking" ? "Thinking" : "Idle";

    return (
      <div className="chat-grid">
        <section className="panel chat-panel">
          <header className="panel-header">
            <h2>Konversation</h2>
            <p>{status}</p>
          </header>

          <div className="conversation-viewport">
            <div className={`conversation-orb ${assistantMode}`} aria-hidden="true">
              <div className="conversation-orb-rings">
                <span />
                <span />
                <span />
              </div>
              <div className="conversation-orb-core" />
              <small>{assistantModeLabel}</small>
            </div>

            <div className="messages">
              {sortedMessages.map((message) => (
                <MessageBubble key={message.id} message={message} onSpeak={handleSpeakMessage} />
              ))}

              {draftMessages.map((draft) => (
                <DraftBubble key={draft.runId} draft={draft} />
              ))}
            </div>
          </div>

          <form className="composer" onSubmit={onSubmit}>
            <div className="quick-actions">
              <p>Quick Actions</p>
              <div className="quick-actions-grid">
                {QUICK_ACTIONS.map((action) => (
                  <button
                    key={action.label}
                    type="button"
                    className="secondary quick-action-button"
                    onClick={() => {
                      void runQuickAction(action.prompt);
                    }}
                    disabled={!sessionId}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
              <small>Voice-Modus reagiert nur auf Saetze, die mit `Jarvis ...` beginnen.</small>
            </div>

            <textarea
              ref={composerInputRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Schreibe eine Aufgabe an Jarvis oder nutze den Sprachmodus..."
              rows={3}
            />
            <div className="actions">
              <button
                type="button"
                className={`record ${voiceModeEnabled ? "active" : ""}`}
                onClick={() => {
                  if (voiceModeEnabled) {
                    stopVoiceMode();
                  } else {
                    void startVoiceMode();
                  }
                }}
              >
                {voiceModeEnabled ? "Sprachmodus stoppen" : "Sprachmodus starten"}
              </button>

              <button
                type="button"
                className={voiceRepliesEnabled ? "" : "secondary"}
                onClick={() => setVoiceRepliesEnabled((previous) => !previous)}
              >
                {voiceRepliesEnabled ? "Antwort: Sprache" : "Text only"}
              </button>

              <button type="submit" disabled={busy || !sessionId}>
                {busy ? "Läuft..." : "Senden"}
              </button>
            </div>
          </form>
        </section>

        <section className="panel timeline">
          <header className="panel-header">
            <h2>Aktivität</h2>
            <p>Live Run-States des Agenten</p>
          </header>

          <ul>
            {deferredTimeline.map((item) => (
              <TimelineRow key={item.id} item={item} />
            ))}
            {!deferredTimeline.length ? <li className="empty">Noch keine Aktivität</li> : null}
          </ul>
        </section>
      </div>
    );
  }

  function renderApprovalsTab() {
    return (
      <section className="panel approvals">
        <header className="panel-header">
          <h2>Freigaben</h2>
          <p>Jede Aktion benötigt explizite Zustimmung.</p>
        </header>

        <div className="panel-scroll approvals-scroll">
          {!approvals.length ? <p className="empty">Keine offenen Freigaben.</p> : null}

          {approvals.map((approval) => (
            <article key={approval.id} className="approval-card">
              <h3>{approval.tool_name}</h3>
              <p>Run: {approval.run_id}</p>
              <pre>{formatJson(approval.tool_input)}</pre>
              <div className="approval-actions">
                <button onClick={() => handleApproval(approval.id, "approve")}>Approve</button>
                <button className="secondary" onClick={() => handleApproval(approval.id, "deny")}>Deny</button>
              </div>
            </article>
          ))}
        </div>
      </section>
    );
  }

  function renderSettingsTab() {
    const isSayEngine = settingsDraft.tts_engine.trim().toLowerCase() === "say";
    const currentVoiceMissingFromList =
      settingsDraft.tts_voice.trim().length > 0 && !sayVoices.includes(settingsDraft.tts_voice);

    return (
      <section className="panel settings">
        <header className="panel-header">
          <h2>Settings</h2>
          <p>Lokal persistiert in SQLite.</p>
        </header>

        <div className="panel-scroll settings-scroll">
          <div className="form-grid">
            <label>
              Modell
              <input
                value={settingsDraft.model_name}
                onChange={(event) => setSettingsDraft((previous) => ({ ...previous, model_name: event.target.value }))}
              />
            </label>

            <label>
              Sprache
              <input
                value={settingsDraft.language}
                onChange={(event) => setSettingsDraft((previous) => ({ ...previous, language: event.target.value }))}
              />
            </label>

            <label>
              Ollama URL
              <input
                value={settingsDraft.ollama_base_url}
                onChange={(event) => setSettingsDraft((previous) => ({ ...previous, ollama_base_url: event.target.value }))}
              />
            </label>

            <label>
              TTS Engine
              <input
                value={settingsDraft.tts_engine}
                onChange={(event) => setSettingsDraft((previous) => ({ ...previous, tts_engine: event.target.value }))}
              />
            </label>

            <label>
              Piper Modellpfad
              <input
                value={settingsDraft.tts_model_path}
                onChange={(event) => setSettingsDraft((previous) => ({ ...previous, tts_model_path: event.target.value }))}
              />
            </label>

            <label>
              TTS Voice
              {isSayEngine ? (
                <div className="tts-voice-row">
                  <select
                    value={settingsDraft.tts_voice}
                    onChange={(event) =>
                      setSettingsDraft((previous) => ({ ...previous, tts_voice: event.target.value }))
                    }
                  >
                    {currentVoiceMissingFromList ? (
                      <option value={settingsDraft.tts_voice}>
                        {settingsDraft.tts_voice} (aktuell)
                      </option>
                    ) : null}
                    {sayVoices.map((voice) => (
                      <option key={voice} value={voice}>
                        {voice}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => {
                      refreshAudioVoices().catch((error) => setStatus((error as Error).message));
                    }}
                  >
                    Neu laden
                  </button>
                </div>
              ) : (
                <input
                  value={settingsDraft.tts_voice}
                  onChange={(event) => setSettingsDraft((previous) => ({ ...previous, tts_voice: event.target.value }))}
                />
              )}
            </label>

            <label>
              say Rate (WPM)
              <input
                type="number"
                min={80}
                max={420}
                value={settingsDraft.say_rate_wpm}
                onChange={(event) =>
                  setSettingsDraft((previous) => ({
                    ...previous,
                    say_rate_wpm: Number.isFinite(Number(event.target.value))
                      ? Number(event.target.value)
                      : previous.say_rate_wpm
                  }))
                }
              />
            </label>

            <label>
              Sir Aussprache (TTS)
              <input
                value={settingsDraft.tts_sir_pronunciation}
                onChange={(event) =>
                  setSettingsDraft((previous) => ({ ...previous, tts_sir_pronunciation: event.target.value }))
                }
                placeholder="Sör"
              />
            </label>

            <label>
              Whisper Modellpfad
              <input
                value={settingsDraft.whisper_model_path}
                onChange={(event) => setSettingsDraft((previous) => ({ ...previous, whisper_model_path: event.target.value }))}
              />
            </label>

            <label>
              Whisper Binary
              <input
                value={settingsDraft.whisper_binary}
                onChange={(event) => setSettingsDraft((previous) => ({ ...previous, whisper_binary: event.target.value }))}
              />
            </label>
          </div>

          <div className="allowlist">
            <h3>Allowed Paths</h3>
            <div className="allowlist-add">
              <input
                value={allowlistInput}
                onChange={(event) => setAllowlistInput(event.target.value)}
                placeholder="/Users/.../Dokumente"
              />
              <button onClick={addAllowlistPath}>Hinzufügen</button>
            </div>

            <ul>
              {settingsDraft.allowed_paths.map((path) => (
                <li key={path}>
                  <code>{path}</code>
                  <button className="secondary" onClick={() => removeAllowlistPath(path)}>
                    Entfernen
                  </button>
                </li>
              ))}
              {!settingsDraft.allowed_paths.length ? <li className="empty">Keine Allowlist-Pfade gesetzt.</li> : null}
            </ul>
          </div>
        </div>

        <div className="settings-footer">
          <button onClick={handleSaveSettings}>Speichern</button>
          <span>Aktiv: {settings.model_name}</span>
        </div>
      </section>
    );
  }

  function renderSmartHomeTab() {
    return (
      <section className="panel smarthome">
        <header className="panel-header">
          <h2>Smart Home (Template)</h2>
          <p>Stub-Provider für spätere Home Assistant Integration.</p>
        </header>

        <div className="panel-scroll smarthome-scroll">
          <div className="entity-grid">
            {entities.map((entity) => (
              <article key={entity.id} className="entity-card">
                <h3>{entity.name}</h3>
                <p>{entity.entity_type}</p>
                <strong>Status: {entity.state}</strong>
                <div className="entity-actions">
                  <button onClick={() => handleSmartHomeAction(entity.id, "toggle")}>Toggle</button>
                  <button onClick={() => handleSmartHomeAction(entity.id, "turn_on")}>On</button>
                  <button className="secondary" onClick={() => handleSmartHomeAction(entity.id, "turn_off")}>Off</button>
                </div>
              </article>
            ))}
          </div>

          {!entities.length ? <p className="empty">Keine Entities gefunden.</p> : null}
        </div>
      </section>
    );
  }

  return (
    <main className="app-shell">
      <div className="fx-noise" aria-hidden="true" />
      <header className="app-header">
        <div className="brand-block">
          <h1>YJARVIS // LOCAL CORE</h1>
          <p>Offline assistant runtime with transparent, approval-based actions.</p>
        </div>
        <div className="core-orb" aria-hidden="true" />
        <div className="header-actions">
          <button
            type="button"
            className="secondary command-button"
            onClick={() => {
              setCommandPaletteOpen(true);
            }}
          >
            Command
            <kbd>⌘K</kbd>
          </button>
          <div className="env-pill">
            {window.jarvisDesktop?.platform || "web"} · Electron {window.jarvisDesktop?.versions.electron || "-"}
          </div>
        </div>
      </header>

      <section className="status-strip">
        <article className={`status-chip ${voiceModeEnabled ? "live" : ""}`}>
          <span>Voice Input</span>
          <strong>{voiceModeEnabled ? "Armed" : "Standby"}</strong>
        </article>
        <article className={`status-chip ${assistantMode === "speaking" ? "live" : ""}`}>
          <span>Core</span>
          <strong>{assistantMode}</strong>
        </article>
        <article className={`status-chip ${isTabPending ? "live" : ""}`}>
          <span>UI Render</span>
          <strong>{isTabPending ? "Switching" : "Stable"}</strong>
        </article>
        <article className="status-chip">
          <span>Reply Mode</span>
          <strong>{voiceRepliesEnabled ? "Voice + Text" : "Text Only"}</strong>
        </article>
        <article className="status-chip">
          <span>Model</span>
          <strong>{shortModelName(settings.model_name)}</strong>
        </article>
        <article className="status-chip">
          <span>STT</span>
          <strong>{fileNameFromPath(settings.whisper_model_path)}</strong>
        </article>
        <article className="status-chip">
          <span>Session</span>
          <strong>{sessionId ? sessionId.slice(0, 8) : "booting"}</strong>
        </article>
      </section>

      <nav className="tabs">
        <button className={activeTab === "chat" ? "active" : ""} onClick={() => switchTab("chat")}>Chat</button>
        <button className={activeTab === "approvals" ? "active" : ""} onClick={() => switchTab("approvals")}>Approvals</button>
        <button className={activeTab === "settings" ? "active" : ""} onClick={() => switchTab("settings")}>Settings</button>
        <button className={activeTab === "smarthome" ? "active" : ""} onClick={() => switchTab("smarthome")}>Smart Home</button>
      </nav>

      <section className="tab-content">
        {activeTab === "chat" ? renderChatTab() : null}
        {activeTab === "approvals" ? renderApprovalsTab() : null}
        {activeTab === "settings" ? renderSettingsTab() : null}
        {activeTab === "smarthome" ? renderSmartHomeTab() : null}
      </section>

      <CommandPalette
        open={commandPaletteOpen}
        query={commandQuery}
        items={filteredCommandItems}
        onQueryChange={setCommandQuery}
        onClose={() => {
          setCommandPaletteOpen(false);
          setCommandQuery("");
        }}
        onRun={runCommandItem}
      />
    </main>
  );
}

export default App;
