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
  wsUrl,
  type ChatMessage
} from "./api";
import { AppShell, type TabId } from "./app/AppShell";
import { PresenceStage, runStateLabel } from "./app/PresenceStage";
import { AppFeedback, type ConnectionState, type FailureKind, type Failures } from "./app/AppFeedback";
import { ActionReview } from "./app/ActionReview";
import { SetupNotice } from "./setup/SetupStatusView";
import type { SetupCheck } from "./setup/types";
import { IntelligentSettings } from "./components/IntelligentSettings";
import { microphoneConstraints, microphoneErrorMessage, persistMicrophonePreference, readMicrophonePreference } from "./voice/microphoneDevices";
import { ChatSubmissionError } from "./api";
import {
  TerminalRunHistory,
  VoiceActivation,
  VoiceSubmissionQueue,
  nextLocalMessageId,
  type VoiceSubmission
} from "./voice/voiceReliability";

type AssistantMode = "idle" | "thinking" | "speaking";

type CommandItem = {
  id: string;
  label: string;
  hint: string;
  keywords: string[];
  run: () => void;
  disabled?: boolean;
};

type TimelineEntry = {
  id: string;
  runId: string;
  state: string;
  detail?: string;
  timestamp: string;
};

type CaptureStopReason = "silence" | "max" | "manual" | "tts" | "cancel";
type RecordedCapture = {
  id: number;
  activation: VoiceActivation;
  sequence: number;
  assistantTextAtStart: string;
  recentAssistantAtStart: number;
  recorder: MediaRecorder;
  chunks: Blob[];
  startedAt: number;
  speechStartedAt: number | null;
  hadSpeech: boolean;
  stopReason: CaptureStopReason | null;
  finalized: boolean;
};

type ActiveChatRun = {
  source: "text" | "voice";
  runId: string | null;
  interrupted: boolean;
};

function whisperSetupHint(reason: string): string {
  if (reason === "whisper_cli_missing") return "Whisper CLI fehlt. Bitte im Guided Setup installieren.";
  if (reason === "ffmpeg_missing") return "ffmpeg fehlt. Bitte im Guided Setup installieren.";
  if (reason === "model_file_missing" || reason === "model_file_invalid") {
    return "Whisper-Modell fehlt oder ist ungültig. Bitte im Guided Setup auswählen.";
  }
  return "Spracherkennung nicht bereit (" + reason + "). Bitte Guided Setup prüfen.";
}

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

let lastLocalMessageId = 0;
function uniqueMessageId() {
  lastLocalMessageId = nextLocalMessageId(lastLocalMessageId, Date.now());
  return lastLocalMessageId;
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

function isRecentShortAssistantWakeEcho(
  transcript: string,
  assistantText: string,
  assistantAt: number,
  capturedAt: number
): boolean {
  const normalized = normalizeForEchoCheck(transcript);
  const assistant = normalizeForEchoCheck(assistantText);
  return WAKE_WORD_ONLY_PATTERNS.includes(normalized) && assistant.startsWith(normalized) &&
    assistantAt > 0 && capturedAt >= assistantAt && capturedAt - assistantAt <= 1_200;
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
        <time>Antwort entsteht</time>
      </header>
      <p>{draft.content || "..."}</p>
    </article>
  );
});

const TimelineRow = memo(function TimelineRow({ item }: { item: TimelineEntry }) {
  return (
    <li>
      <div>
        <strong className={`state-badge state-${item.state}`}>{runStateLabel(item.state)}</strong>
      </div>
      <time>{new Date(item.timestamp).toLocaleTimeString()}</time>
      <details className="technical-details"><summary>Ereignisdetails</summary><p>{item.detail || "Keine weiteren Angaben."}</p><code>{item.state} · {item.runId}</code></details>
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
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement;
    const dialog = dialogRef.current;
    dialog?.showModal();
    dialog?.querySelector<HTMLInputElement>("input")?.focus();
    return () => {
      dialog?.close();
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
  }, [open]);

  if (!open) {
    return null;
  }

  return (
    <dialog ref={dialogRef} className="command-palette-overlay" aria-label="Jarvis Kommandos" onCancel={(event) => { event.preventDefault(); onClose(); }} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div
        className="command-palette"
        onClick={(event) => {
          event.stopPropagation();
        }}
      >
        <header>
          <div><p className="eyebrow">Direkt zu deinem nächsten Schritt</p><h3>Jarvis Kommandos</h3></div>
          <button type="button" className="secondary" onClick={onClose} aria-label="Kommandos schließen">Esc</button>
        </header>
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          aria-label="Kommandos durchsuchen"
          placeholder="Aktion, Arbeitsbereich oder Sprachmodus …"
        />
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <button
                className="secondary"
                type="button"
                disabled={item.disabled}
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
    </dialog>
  );
});

function App({ setupCheck, onRecheckSetup }: { setupCheck: SetupCheck; onRecheckSetup: () => Promise<void> }) {
  const chatAvailable = setupCheck.state === "ready" || setupCheck.state === "degraded";
  const sttUnavailable = !!setupCheck.report && setupCheck.report.stt.status !== "available";
  const chatAvailableRef = useRef(chatAvailable);
  chatAvailableRef.current = chatAvailable;
  const [activeTab, setActiveTab] = useState<TabId>("chat");
  const [sessionId, setSessionId] = useState<string>("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [draftByRun, setDraftByRun] = useState<Record<string, string>>({});
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Starte lokale Session...");
  const [connection, setConnection] = useState<ConnectionState>({ phase: "starting" });
  const [failures, setFailures] = useState<Failures>({});

  function reportFailure(kind: FailureKind, title: string, error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    setStatus(message);
    setFailures((previous) => ({ ...previous, [kind]: { title, message } }));
  }

  function dismissFailure(kind: FailureKind) {
    setFailures((previous) => {
      const next = { ...previous };
      delete next[kind];
      return next;
    });
  }

  const [approvals, setApprovals] = useState<Approval[]>([]);

  const [settings, setSettings] = useState<JarvisSettings>(DEFAULT_SETTINGS);
  const [settingsDraft, setSettingsDraft] = useState<JarvisSettings>(DEFAULT_SETTINGS);
  const [allowlistInput, setAllowlistInput] = useState("");
  const [sayVoices, setSayVoices] = useState<string[]>([]);
  const [selectedMicrophoneId, setSelectedMicrophoneId] = useState(readMicrophonePreference);

  useEffect(() => { persistMicrophonePreference(selectedMicrophoneId); }, [selectedMicrophoneId]);

  const [entities, setEntities] = useState<SmartHomeEntity[]>([]);

  const [voiceModeEnabled, setVoiceModeEnabled] = useState(false);
  const [voiceRepliesEnabled, setVoiceRepliesEnabled] = useState(true);
  const [voiceTranscriptPreview, setVoiceTranscriptPreview] = useState("");
  const [voiceStage, setVoiceStage] = useState("");
  const [voiceEntries, setVoiceEntries] = useState<VoiceSubmission[]>([]);
  const [assistantMode, setAssistantMode] = useState<AssistantMode>("idle");
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const [isTabPending, startTabTransition] = useTransition();

  const busyRef = useRef(false);
  const voiceRepliesEnabledRef = useRef(true);
  const ttsPlaybackActiveRef = useRef(false);
  const suppressVoiceInputUntilRef = useRef(0);
  const lastAssistantSpokenTextRef = useRef("");
  const lastAssistantSpeechAtRef = useRef(0);
  const activeChatRunRef = useRef<ActiveChatRun | null>(null);
  const terminalRunsRef = useRef(new TerminalRunHistory());
  const [runUncertain, setRunUncertain] = useState(false);

  const voiceQueueRef = useRef(new VoiceSubmissionQueue());
  const voiceFlushRunningRef = useRef(false);
  const voiceActivationRef = useRef<VoiceActivation | null>(null);
  const ttsQueueRef = useRef<string[]>([]);
  const ttsQueueRunningRef = useRef(false);
  const spokenOffsetByRunRef = useRef<Record<string, number>>({});
  const thinkingRunsRef = useRef<Set<string>>(new Set());

  const voiceModeEnabledRef = useRef(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const activeCaptureRef = useRef<RecordedCapture | null>(null);
  const captureCounterRef = useRef(0);
  const voiceStartInProgressRef = useRef(false);
  const voiceStartGenerationRef = useRef(0);
  const voiceDisposedRef = useRef(false);

  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const analyserDataRef = useRef<Uint8Array<ArrayBuffer> | null>(null);
  const monitorRafRef = useRef<number | null>(null);
  const composerInputRef = useRef<HTMLTextAreaElement | null>(null);

  const lastSpeechAtRef = useRef(0);
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

    if (voiceModeEnabledRef.current) requestRecorderStop("tts");

    try {
      lastAssistantSpokenTextRef.current = nextChunk;
      lastAssistantSpeechAtRef.current = Date.now();
      await speak(nextChunk);
    } catch (error) {
      reportFailure("voice", "Sprachausgabe fehlgeschlagen", error);
    } finally {
      ttsPlaybackActiveRef.current = false;
      ttsQueueRunningRef.current = false;
      lastAssistantSpeechAtRef.current = Date.now();
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
    activeChatRunRef.current = null;
    setRunUncertain(false);
    busyRef.current = false;
    setBusy(false);
    syncAssistantMode();
  }

  function noteTerminalRun(runId: string, state: "done" | "error") {
    terminalRunsRef.current.remember(runId, state);
    const active = activeChatRunRef.current;
    // Events belonging to older or unrelated runs must never release this run.
    if (!active || active.runId !== runId) return;
    releaseBusyLock();
    if (active.source === "voice") {
      setVoiceStage(state === "done" ? "Agent-Run abgeschlossen" : "Agent-Run fehlgeschlagen");
    }
  }

  function registerRunAcknowledgement(active: ActiveChatRun, runId: string) {
    if (activeChatRunRef.current !== active) return;
    active.runId = runId;
    const earlyTerminal = terminalRunsRef.current.get(runId);
    if (earlyTerminal) {
      // WebSocket can beat /v1/chat HTTP. No watchdog for a finished run.
      noteTerminalRun(runId, earlyTerminal);
      return;
    }
    if (active.interrupted) {
      setRunUncertain(true);
      if (active.source === "voice") {
        setVoiceStage("Agent-Run angenommen · Abschluss nach Verbindungsabbruch unbekannt");
      }
      return;
    }
    armBusyWatchdog(runId);
  }

  function armBusyWatchdog(runId: string) {
    clearBusyWatchdog();
    busyWatchdogTimerRef.current = window.setTimeout(() => {
      const active = activeChatRunRef.current;
      if (!active || active.runId !== runId || terminalRunsRef.current.get(runId)) return;
      // Timeout does not prove server completion; retain the voice queue lock.
      active.interrupted = true;
      setRunUncertain(true);
      if (active.source === "voice") {
        setVoiceStage("Agent-Run nicht bestätigt · Warteschlange pausiert");
      }
      reportFailure("chat", "Agent-Abschluss nicht bestätigt",
        "Der Agent-Run hat seit 45 Sekunden keinen nachgewiesenen Abschluss. Bitte Run prüfen.");
    }, RUN_COMPLETION_TIMEOUT_MS);
  }

  function continueAfterManualRunCheck() {
    const active = activeChatRunRef.current;
    if (!active?.interrupted || !active.runId) return;
    if (!window.confirm(
      "Der angenommene Agent-Run könnte noch arbeiten. Hast du seinen Status geprüft und möchtest " +
      "die nächsten Befehle trotzdem bewusst freigeben?"
    )) return;
    setVoiceStage("Run-Status vom Benutzer geprüft · Warteschlange freigegeben");
    releaseBusyLock();
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

  function requestRecorderStop(reason: CaptureStopReason) {
    const capture = activeCaptureRef.current;
    if (!capture || capture.recorder.state === "inactive") return;
    // Reason belongs to the recorder generation; stop() never discards captured chunks.
    if (!capture.stopReason) capture.stopReason = reason;
    try {
      capture.recorder.stop();
    } catch (error) {
      reportFailure("voice", "Audioaufnahme konnte nicht beendet werden", error);
    }
  }

  function stopVoiceModeInternal({ updateStatus, cancel = false }: { updateStatus: boolean; cancel?: boolean }) {
    voiceStartGenerationRef.current += 1;
    voiceModeEnabledRef.current = false;
    setVoiceModeEnabled(false);
    requestRecorderStop(cancel ? "cancel" : "manual");
    const activation = voiceActivationRef.current;
    voiceActivationRef.current = null;
    // Do not reset a stopped generation's wake permission: its already-recorded
    // segments may still need to finish STT in capture order after Stop.
    // The next Start always gets an independent VoiceActivation.
    if (cancel) activation?.cancel();

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    shutdownAudioNodes();
    if (updateStatus) {
      setStatus("Sprachmodus aus; gültige Audiosegmente werden fertig verarbeitet.");
      setVoiceStage("Mikrofon aus · ausstehende Aufnahme wird verarbeitet");
    }
  }

  async function submitMessage(message: string, source: "text" | "voice"): Promise<boolean> {
    if (!chatAvailableRef.current) {
      return false;
    }
    const trimmed = message.trim();
    if (!trimmed || !sessionId || busyRef.current) {
      return false;
    }

    busyRef.current = true;
    setBusy(true);
    const active: ActiveChatRun = { source, runId: null, interrupted: false };
    activeChatRunRef.current = active;
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
      const acknowledged = await sendChat(sessionId, trimmed);
      registerRunAcknowledgement(active, acknowledged.run_id);
      return true;
    } catch (error) {
      if (activeChatRunRef.current === active) releaseBusyLock();
      reportFailure("chat", "Nachricht konnte nicht gesendet werden", error);
      return false;
    }
  }

  function refreshVoiceEntries() {
    setVoiceEntries(voiceQueueRef.current.snapshot());
  }

  async function flushVoiceQueue() {
    if (!chatAvailableRef.current || voiceDisposedRef.current) return;
    if (voiceFlushRunningRef.current || busyRef.current || !sessionId) return;
    const next = voiceQueueRef.current.claimNext();
    if (!next) return;
    voiceFlushRunningRef.current = true;
    refreshVoiceEntries();
    busyRef.current = true;
    setBusy(true);
    const active: ActiveChatRun = { source: "voice", runId: null, interrupted: false };
    activeChatRunRef.current = active;
    setVoiceStage("Befehl wird an den Agent gesendet");
    syncAssistantMode();
    try {
      const acknowledged = await sendChat(sessionId, next.command);
      voiceQueueRef.current.settle(next.id, "accepted", acknowledged.run_id);
      // Voice transcripts are shown in the queue before POST, in Chat only after ACK.
      // If a user consciously retries after an unknown result, only one chat bubble
      // is shown per utterance even if the backend cannot guarantee exactly once.
      setMessages((previous) => {
        if (previous.some((item) => item.id === Number(next.id))) return previous;
        return [...previous, {
          id: Number(next.id), role: "user", content: next.command,
          created_at: new Date().toISOString()
        }];
      });
      registerRunAcknowledgement(active, acknowledged.run_id);
      if (activeChatRunRef.current === active) {
        setVoiceStage(active.interrupted
          ? "Agent-Run angenommen · Abschluss nach Verbindungsabbruch unbekannt"
          : "Befehl vom Agent angenommen");
      }
    } catch (error) {
      const rejected = error instanceof ChatSubmissionError && error.outcome === "rejected";
      voiceQueueRef.current.settle(next.id, rejected ? "failed" : "pending",
        error instanceof Error ? error.message : String(error));
      setVoiceStage(rejected
        ? "Chat hat den Befehl abgelehnt · erneutes Senden möglich"
        : "Übermittlung unklar · bitte vor erneutem Senden prüfen");
      if (activeChatRunRef.current === active) releaseBusyLock();
      reportFailure("chat", "Sprachbefehl nicht bestätigt", error);
    } finally {
      voiceFlushRunningRef.current = false;
      refreshVoiceEntries();
    }
    // Accepted requests retain the busy lock until the normal response lifecycle.
    // Failed/uncertain head entries block following commands; never retry in a loop.
    if (!busyRef.current && chatAvailableRef.current) void flushVoiceQueue();
  }

  function enqueueVoiceMessage(id: string, transcript: string, command: string, capturedAt: number) {
    if (voiceDisposedRef.current) return;
    voiceQueueRef.current.add(id, transcript, command, capturedAt);
    refreshVoiceEntries();
    setVoiceStage(chatAvailableRef.current ? "Transkript erkannt · Bereit zur Übergabe" :
      "Transkript erkannt · Chat momentan nicht verfügbar (wartet)");
    void flushVoiceQueue();
  }

  function retryVoiceMessage(id: string) {
    const entry = voiceQueueRef.current.snapshot().find((item) => item.id === id);
    if (!entry) return;
    if (entry.state === "pending" && !window.confirm(
      "Die vorherige Übermittlung könnte bereits ausgeführt worden sein. Trotzdem bewusst erneut senden?"
    )) return;
    if (voiceQueueRef.current.retryByUser(id)) {
      refreshVoiceEntries();
      void flushVoiceQueue();
    }
  }

  function discardVoiceMessage(id: string) {
    if (voiceQueueRef.current.discardByUser(id)) {
      refreshVoiceEntries();
      setVoiceStage("Ausstehende Eingabe bewusst verworfen");
      void flushVoiceQueue();
    }
  }

  async function handleRecordedSegment(blob: Blob, capture: RecordedCapture) {
    if (blob.size === 0 || voiceDisposedRef.current) return;
    try {
      setStatus("Transkribiere Audio lokal...");
      setVoiceStage("Sprache aufgenommen · Whisper transkribiert");
      const result = await transcribe(blob);
      if (voiceDisposedRef.current) return;
      const text = result.text.trim();
      if (!text) {
        setVoiceStage("Keine Sprache erkannt");
        setStatus("Keine Sprache erkannt.");
        return;
      }
      setVoiceTranscriptPreview(text);
      // Echo comparison uses the assistant audio that existed when the microphone
      // recorded this segment, not a newer TTS chunk spoken during slow Whisper.
      if (isLikelyEchoTranscript(text, capture.assistantTextAtStart) ||
          isRecentShortAssistantWakeEcho(
            text, capture.assistantTextAtStart, capture.recentAssistantAtStart, capture.startedAt
          )) {
        setVoiceStage("Eigenes Lautsprecher-Echo verworfen");
        return;
      }
      if (shouldIgnoreTranscriptArtifact(text) && !WAKE_WORD_ONLY_PATTERNS.includes(normalizeForEchoCheck(text))) {
        setVoiceStage("Unsichere Spracherkennung verworfen");
        return;
      }
      const decision = capture.activation.wake.accept(text, capture.speechStartedAt ?? capture.startedAt);
      const isCurrentActivation = voiceActivationRef.current === capture.activation;
      if (decision.kind === "wake") {
        if (isCurrentActivation) {
          setVoiceStage("Wakeword erkannt · Warte auf Folgebefehl (8 Sekunden)");
          setStatus("Jarvis erkannt. Bitte jetzt den Auftrag sprechen.");
        }
        return;
      }
      if (decision.kind === "ignored") {
        if (isCurrentActivation) {
          setVoiceStage("Ohne Wakeword ignoriert · bitte „Jarvis“ sagen");
          setStatus("Ignoriert: Bitte zuerst „Jarvis“ sagen.");
        }
        return;
      }
      setStatus(`Erkannt (${result.latency_ms} ms): ${decision.command}`);
      enqueueVoiceMessage(String(uniqueMessageId()), text, decision.command, capture.speechStartedAt ?? capture.startedAt);
    } catch (error) {
      if (voiceDisposedRef.current) return;
      setVoiceStage("Whisper-Fehler · bitte Eingabe erneut sprechen");
      reportFailure("voice", "Spracherkennung fehlgeschlagen", error);
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
    if (!stream || !voiceModeEnabledRef.current || isVoiceInputSuppressed()) return;
    // Keep the previous recorder until onstop has consumed its final dataavailable.
    if (mediaRecorderRef.current) return;

    const mimeType = pickRecorderMimeType();
    const recorderOptions: MediaRecorderOptions = { audioBitsPerSecond: 128_000 };
    if (mimeType) recorderOptions.mimeType = mimeType;
    const activation = voiceActivationRef.current;
    if (!activation) return;
    const recorder = new MediaRecorder(stream, recorderOptions);
    const capture: RecordedCapture = {
      id: ++captureCounterRef.current,
      activation,
      sequence: activation.allocateSegment(),
      assistantTextAtStart: lastAssistantSpokenTextRef.current,
      recentAssistantAtStart: lastAssistantSpeechAtRef.current,
      recorder,
      chunks: [],
      startedAt: Date.now(),
      speechStartedAt: null,
      hadSpeech: false,
      stopReason: null,
      finalized: false
    };
    activeCaptureRef.current = capture;
    mediaRecorderRef.current = recorder;
    lastSpeechAtRef.current = capture.startedAt;
    silenceFrameCountRef.current = 0;
    voiceGateOpenRef.current = false;

    recorder.ondataavailable = (event) => {
      if (!capture.finalized && event.data.size > 0) capture.chunks.push(event.data);
    };

    recorder.onerror = () => {
      capture.stopReason = "cancel";
      reportFailure("voice", "Fehler bei der Mikrofonaufnahme", "MediaRecorder hat einen Aufnahmefehler gemeldet.");
      // Browser error events are normally followed by a final dataavailable/onstop.
    };

    recorder.onstop = () => {
      if (capture.finalized) return;
      capture.finalized = true;
      if (activeCaptureRef.current === capture) activeCaptureRef.current = null;
      if (mediaRecorderRef.current === recorder) mediaRecorderRef.current = null;
      const blob = new Blob(capture.chunks, { type: recorder.mimeType || mimeType || "audio/webm" });
      capture.chunks = [];
      const duration = Date.now() - capture.startedAt;
      // On manual stop, retain a plausible utterance even if local VAD missed
      // a quiet word. Empty recordings, cancelled captures and TTS echo remain gated.
      const eligible = capture.stopReason !== "cancel" && blob.size > 0 &&
        (capture.hadSpeech || (capture.stopReason === "manual" && duration >= MIN_SEGMENT_MS));
      if (eligible) {
        capture.activation.segments.complete(capture.sequence, async () => {
          await handleRecordedSegment(blob, capture);
        });
      } else {
        capture.activation.segments.skip(capture.sequence);
      }
      if (voiceModeEnabledRef.current && mediaStreamRef.current) resumeRecorderAfterSuppression();
    };

    try {
      recorder.start(1000);
    } catch (error) {
      if (activeCaptureRef.current === capture) activeCaptureRef.current = null;
      if (mediaRecorderRef.current === recorder) mediaRecorderRef.current = null;
      capture.finalized = true;
      capture.activation.segments.skip(capture.sequence);
      throw error;
    }
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
      const capture = activeCaptureRef.current;

      if (!analyser || !data || !recorder || !capture || capture.recorder !== recorder || recorder.state !== "recording") {
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
        if (!capture.hadSpeech) capture.speechStartedAt = now;
        capture.hadSpeech = true;
        lastSpeechAtRef.current = now;
        silenceFrameCountRef.current = 0;
      } else {
        voiceGateOpenRef.current = false;
        if (capture.hadSpeech) {
          silenceFrameCountRef.current += 1;
        }
      }

      const elapsed = now - capture.startedAt;
      const silenceElapsed = now - lastSpeechAtRef.current;

      const shouldCutBySilence =
        capture.hadSpeech &&
        silenceElapsed >= SILENCE_TIMEOUT_MS &&
        silenceFrameCountRef.current >= SILENCE_CONFIRM_FRAMES &&
        elapsed >= MIN_SEGMENT_MS;

      const shouldCutByMaxLength = elapsed >= MAX_SEGMENT_MS;

      if (shouldCutBySilence || shouldCutByMaxLength) {
        requestRecorderStop(shouldCutBySilence ? "silence" : "max");
      }

      monitorRafRef.current = requestAnimationFrame(loop);
    };

    monitorRafRef.current = requestAnimationFrame(loop);
  }

  async function startVoiceMode() {
    if (!chatAvailableRef.current || voiceModeEnabledRef.current || voiceStartInProgressRef.current) return;
    const stt = setupCheck.report?.stt;
    if (stt && stt.status !== "available") {
      const hint = whisperSetupHint(stt.reason);
      setVoiceStage(hint);
      reportFailure("voice", "Spracherkennung nicht verfügbar", hint);
      return;
    }

    const attempt = ++voiceStartGenerationRef.current;
    voiceStartInProgressRef.current = true;
    let stream: MediaStream | null = null;
    let context: AudioContext | null = null;
    try {
      setVoiceStage("Mikrofon wird initialisiert");
      stream = await navigator.mediaDevices.getUserMedia(microphoneConstraints(selectedMicrophoneId));
      stream.getAudioTracks?.().forEach(track => track.addEventListener?.("ended", () => {
        if (voiceModeEnabledRef.current && mediaStreamRef.current === stream) {
          stopVoiceModeInternal({ updateStatus: true });
          reportFailure("voice", "Mikrofon wurde getrennt",
            "Die Audioverbindung wurde unterbrochen. Aufnahme wird sicher beendet; Gerät in Einstellungen prüfen.");
        }
      }));
      if (voiceDisposedRef.current || !chatAvailableRef.current || attempt !== voiceStartGenerationRef.current) return;

      const browserWindow = window as typeof window & { webkitAudioContext?: typeof AudioContext };
      const AudioContextCtor = browserWindow.AudioContext || browserWindow.webkitAudioContext;
      if (!AudioContextCtor) throw new Error("AudioContext wird in diesem Browser nicht unterstützt.");
      context = new AudioContextCtor();
      const source = context.createMediaStreamSource(stream);
      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);
      await context.resume();
      if (voiceDisposedRef.current || !chatAvailableRef.current || attempt !== voiceStartGenerationRef.current) return;

      audioContextRef.current = context;
      sourceNodeRef.current = source;
      analyserRef.current = analyser;
      analyserDataRef.current = new Uint8Array(analyser.fftSize);
      mediaStreamRef.current = stream;
      // Fresh permission on every activation, never inherited across Stop/Start.
      voiceActivationRef.current = new VoiceActivation(attempt);
      voiceModeEnabledRef.current = true;
      setVoiceModeEnabled(true);
      startRecorderSegment();
      startVoiceMonitor();
      setVoiceStage("Mikrofon aktiv · „Jarvis“ sagen");
      setStatus("Sprachmodus aktiv: Sage „Jarvis“, dann innerhalb von 8 Sekunden deinen Befehl.");
    } catch (error) {
      if (!voiceDisposedRef.current && attempt === voiceStartGenerationRef.current) {
        stopVoiceModeInternal({ updateStatus: false });
        setVoiceStage("Mikrofonfehler · Einstellungen prüfen");
        reportFailure("voice", "Sprachmodus konnte nicht gestartet werden",
          microphoneErrorMessage(error, window.jarvisDesktop?.platform || ""));
      }
    } finally {
      // A failed or cancelled start owns its local stream/context until released.
      if (stream && mediaStreamRef.current !== stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
      if (context && audioContextRef.current !== context) {
        try { await context.close(); } catch { /* Already closed. */ }
      }
      voiceStartInProgressRef.current = false;
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
      reportFailure("voice", "Sprachausgabe fehlgeschlagen", error);
    });
  }, []);

  const commandItems = useMemo<CommandItem[]>(() => {
    const quickActionItems = QUICK_ACTIONS.map((action, index) => ({
      id: `quick-${index}`,
      disabled: !chatAvailable,
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
        label: "Chat öffnen",
        hint: "Zur Chat-Ansicht wechseln",
        keywords: ["nav", "chat", "konversation", "go: chat"],
        run: () => switchTab("chat")
      },
      {
        id: "nav-approvals",
        label: "Freigaben ansehen",
        hint: "Offene Freigaben anzeigen",
        keywords: ["nav", "approvals", "freigaben", "go: approvals"],
        run: () => switchTab("approvals")
      },
      {
        id: "nav-settings",
        label: "Einstellungen öffnen",
        hint: "Agent-Konfiguration öffnen",
        keywords: ["nav", "settings", "config", "einstellungen", "go: settings"],
        run: () => switchTab("settings")
      },
      {
        id: "nav-smarthome",
        label: "Smart Home öffnen",
        hint: "Smart-Home-Vorlage öffnen",
        keywords: ["nav", "smarthome", "template", "go: smart home"],
        run: () => switchTab("smarthome")
      },
      {
        id: "toggle-voice-input",
        disabled: (!chatAvailable || sttUnavailable) && !voiceModeEnabled,
        label: voiceModeEnabled ? "Sprachmodus stoppen" : "Sprachmodus starten",
        hint: voiceModeEnabled ? "Sprachmodus deaktivieren" : "Sprachmodus aktivieren",
        keywords: ["voice", "mic", "input", voiceModeEnabled ? "voice input: stop" : "voice input: start"],
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
        label: voiceRepliesEnabled ? "Nur Textantworten" : "Sprache und Text",
        hint: "Antwortmodus umschalten",
        keywords: ["voice", "reply", "tts", "toggle", "text only", "replies: text only", "replies: voice + text"],
        run: () => setVoiceRepliesEnabled((previous) => !previous)
      }
    ];
  }, [voiceModeEnabled, voiceRepliesEnabled, switchTab, sessionId, busy, chatAvailable, sttUnavailable]);

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
    if (!chatAvailable) {
      // A transient setup recheck is not a user request to destroy transcripts.
      // Capture may stop, but queued and in-flight STT is finalized normally.
      if (voiceModeEnabledRef.current) stopVoiceModeInternal({ updateStatus: false });
      if (voiceQueueRef.current.snapshot().length > 0) {
        setVoiceStage("Chat vorübergehend nicht verfügbar · Eingaben bleiben erhalten");
      }
    } else {
      void flushVoiceQueue();
    }
  }, [chatAvailable]);

  useEffect(() => {
    voiceDisposedRef.current = false;
    let cancelled = false;

    async function bootstrap() {
      try {
        // SetupGate already confirmed the existing backend connection.
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
        if (initialSettings.tts_engine.trim().toLowerCase() === "say") {
          refreshAudioVoices().catch((error) => reportFailure("voice", "Stimmen konnten nicht geladen werden", error));
        }
      } catch (error) {
        if (!cancelled) {
          reportFailure("session", "Session konnte nicht vollständig geladen werden", error);
        }
      }
    }

    bootstrap();

    return () => {
      cancelled = true;
      clearBusyWatchdog();
      clearTokenFlushTimer();
      tokenBufferByRunRef.current = {};
      voiceDisposedRef.current = true;
      stopVoiceModeInternal({ updateStatus: false, cancel: true });
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
    refreshAudioVoices().catch((error) => reportFailure("voice", "Stimmen konnten nicht geladen werden", error));
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
      setConnection({ phase: "retry_wait", seconds: Math.max(1, Math.round(delay / 1000)) });
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
      setConnection({ phase: reconnectAttempt > 0 ? "reconnecting" : "connecting" });
      const nextSocket = new WebSocket(wsUrl(sessionId));
      socket = nextSocket;

      nextSocket.onopen = () => {
        if (cancelled || socket !== nextSocket) return;
        setConnection({ phase: "connected" });
        reconnectAttempt = 0;
        if (activeChatRunRef.current?.interrupted) {
          setRunUncertain(true);
          setStatus("Agent wieder verbunden. Der vorherige Run-Abschluss ist noch ungeklärt.");
        } else {
          setStatus(`Verbunden mit Agent (${sessionId})`);
        }
      };

      nextSocket.onmessage = (event) => {
        if (cancelled || socket !== nextSocket) return;
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
            // A message is not a terminal run_state and might belong to another run.
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
            refreshApprovals().catch((error) => reportFailure("action", "Freigaben konnten nicht geladen werden", error));
          }

          if (payload.state === "done" || payload.state === "error") {
            noteTerminalRun(payload.run_id, payload.state);
            clearStreamingSpeechForRun(payload.run_id);
            refreshApprovals().catch((error) => reportFailure("action", "Freigaben konnten nicht geladen werden", error));
          }
        }
      };

      nextSocket.onerror = () => {
        if (!cancelled && socket === nextSocket) setConnection({ phase: "reconnecting" });
        try {
          nextSocket.close();
        } catch {
          // ignore
        }
      };

      nextSocket.onclose = () => {
        if (cancelled || socket !== nextSocket) {
          return;
        }
        clearTokenFlushTimer();
        tokenBufferByRunRef.current = {};
        thinkingRunsRef.current.clear();
        spokenOffsetByRunRef.current = {};
        syncAssistantMode();
        const active = activeChatRunRef.current;
        if (active) {
          active.interrupted = true;
          clearBusyWatchdog();
          setRunUncertain(true);
          setStatus("Agent-Verbindung unterbrochen · aktiver Run bleibt gesperrt.");
          if (active.source === "voice") {
            setVoiceStage("Agent-Verbindung unterbrochen · weitere Sprachbefehle warten");
          }
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
      reportFailure("action", "Freigabeentscheidung fehlgeschlagen", error);
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
      void onRecheckSetup();
    } catch (error) {
      reportFailure("action", "Einstellungen konnten nicht gespeichert werden", error);
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
      reportFailure("action", "Smart-Home-Aktion fehlgeschlagen", error);
    }
  }

  function renderChatTab() {
    return (
      <div className="chat-grid">
        <section className="panel chat-panel">
          <header className="panel-header">
            <div><p className="eyebrow">Dein Raum für Gedanken</p><h2>Im Gespräch mit Jarvis</h2></div>
            <details className="connection-details"><summary>Verbindung & Hinweise</summary><p>{status}</p></details>
          </header>

          <div className="conversation-viewport">
            <PresenceStage mode={assistantMode} microphoneActive={voiceModeEnabled} latestEvent={timeline[0]} />

            <div className="messages" aria-label="Nachrichten">
              {!sortedMessages.length && !draftMessages.length ? <div className="conversation-empty"><span className="eyebrow">Ein Gedanke. Ein Anfang.</span><h3>Was beschäftigt dich?</h3><p>{chatAvailable ? "Eine Idee ordnen, den Tag planen oder etwas Neues verstehen. Fang einfach an." : "Schau dich in Ruhe um. Sobald ein Chat-Modell bestätigt ist, beginnt hier dein Gespräch mit Jarvis."}</p></div> : null}
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
              <p className="visually-hidden">Schnelle Aufgaben</p>
              <div className="quick-actions-grid">
                {QUICK_ACTIONS.map((action) => (
                  <button
                    key={action.label}
                    type="button"
                    className="secondary quick-action-button"
                    onClick={() => {
                      void runQuickAction(action.prompt);
                    }}
                    disabled={!sessionId || !chatAvailable}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
              <small>„Jarvis, öffne …“ oder „Jarvis“ und anschließend den Auftrag sagen.</small>
            </div>
            {(voiceModeEnabled || voiceStage || voiceEntries.length > 0 || voiceTranscriptPreview || runUncertain) && (
              <div className="voice-reliability-panel" aria-label="Sprachverarbeitung">
                <p role="status" aria-live="polite">
                  {voiceStage || (voiceModeEnabled ? "Mikrofon aktiv" : "Mikrofon aus")}
                </p>
                {runUncertain && (
                  <div>
                    <p>Angenommener Agent-Run ohne bestätigten Abschluss. Nachfolgende Befehle warten.</p>
                    <button type="button" className="secondary"
                      disabled={!activeChatRunRef.current?.runId}
                      onClick={continueAfterManualRunCheck}>
                      Run prüfen und bewusst fortsetzen
                    </button>
                  </div>
                )}
                {voiceTranscriptPreview && (
                  <p className="voice-final-transcript">Letztes Transkript: {voiceTranscriptPreview}</p>
                )}
                {voiceEntries.length > 0 && (
                  <ul aria-label="Sprachbefehle und Übergabestatus">
                    {voiceEntries.map((entry) => (
                      <li key={entry.id}>
                        <span>{entry.command}</span>
                        <small>{entry.state === "accepted" ? "Vom Agent angenommen" :
                          entry.state === "submitting" ? "Wird gesendet" :
                          entry.state === "pending" ? "Ausgang unklar — eventuell bereits ausgeführt" :
                          entry.state === "failed" ? "Abgelehnt — nicht gesendet" :
                          chatAvailable ? "Bereit zum Senden" : "Wartet auf Chat-Verfügbarkeit"}</small>
                        {(entry.state === "pending" || entry.state === "failed") && (
                          <button type="button" className="secondary" onClick={() => retryVoiceMessage(entry.id)}>
                            Erneut senden
                          </button>
                        )}
                        {(entry.state === "ready" || entry.state === "pending" || entry.state === "failed") && (
                          <button type="button" className="secondary" onClick={() => discardVoiceMessage(entry.id)}>
                            Verwerfen
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <textarea
              disabled={!chatAvailable}
              aria-label="Nachricht an Jarvis"
              ref={composerInputRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Was möchtest du gemeinsam angehen?"
              rows={2}
            />
            <div className="actions">
              <button
                type="button"
                className={`record ${voiceModeEnabled ? "active" : ""}`}
                disabled={(!chatAvailable || sttUnavailable) && !voiceModeEnabled}
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
                {voiceRepliesEnabled ? "Antwort: Sprache" : "Antwort: Text"}
              </button>

              <button type="submit" disabled={busy || !sessionId || !chatAvailable}>
                {busy ? "Läuft..." : "Senden"}
              </button>
            </div>
          </form>
        </section>

        <details className="timeline">
          <summary>Verlauf & Ereignisse <span>{deferredTimeline.length}</span></summary>
          <ul>
            {deferredTimeline.map((item) => (
              <TimelineRow key={item.id} item={item} />
            ))}
            {!deferredTimeline.length ? <li className="empty">Noch keine Aktivität</li> : null}
          </ul>
        </details>
      </div>
    );
  }

  function renderApprovalsTab() {
    return (
      <section className="panel approvals">
        <header className="panel-header">
          <h2>Freigaben</h2>
          <p>Diese angefragten Aktionen warten auf deine Entscheidung.</p>
        </header>

        <div className="panel-scroll approvals-scroll">
          {!approvals.length ? <p className="empty">Keine offenen Freigaben.</p> : null}

          {approvals.map((approval) => (
            <ActionReview key={approval.id} approval={approval} onDecide={handleApproval} />
          ))}
        </div>
      </section>
    );
  }

  function renderSettingsTab() {
    return <IntelligentSettings
      settings={settings}
      draft={settingsDraft}
      setDraft={setSettingsDraft}
      setupCheck={setupCheck}
      sayVoices={sayVoices}
      onRefreshVoices={refreshAudioVoices}
      onSave={handleSaveSettings}
      onConfigured={(fields) => {
        void fetchSettings().then(latest => {
          const changed = Object.fromEntries(fields.map(key => [key, latest[key]])) as Partial<JarvisSettings>;
          setSettings(latest);
          // Only fields explicitly written by SetupInstaller merge into the
          // draft. Preserve all unrelated dirty advanced/security settings.
          setSettingsDraft(draft => ({ ...draft, ...changed }));
          void onRecheckSetup();
        }).catch(() => setStatus("Installation erfolgreich; Einstellungen bitte neu laden."));
      }}
      selectedMicId={selectedMicrophoneId}
      onSelectMic={id => {
        if (voiceModeEnabledRef.current || voiceStartInProgressRef.current) {
          stopVoiceModeInternal({ updateStatus: true });
        }
        setSelectedMicrophoneId(id);
      }}
      voiceActive={voiceModeEnabled}
      onMicUnavailable={() => {
        if (voiceModeEnabledRef.current || voiceStartInProgressRef.current) {
          stopVoiceModeInternal({ updateStatus: true });
        }
      }}
      allowlistInput={allowlistInput}
      onAllowlistInput={setAllowlistInput}
      onAddPath={addAllowlistPath}
      onRemovePath={removeAllowlistPath}
    />;
  }

  function renderSmartHomeTab() {
    return (
      <section className="panel smarthome">
        <header className="panel-header">
          <h2>Smart Home · Vorlage</h2>
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
    <>
      <AppShell
        notice={<SetupNotice check={setupCheck} onRetry={() => void onRecheckSetup()} />}
        activeTab={activeTab}
        onNavigate={switchTab}
        onOpenCommands={() => setCommandPaletteOpen(true)}
        runtime={{
          voiceInput: voiceModeEnabled ? "Armed" : "Standby",
          core: assistantMode,
          uiRender: isTabPending ? "Switching" : "Stable",
          replyMode: voiceRepliesEnabled ? "Voice + Text" : "Text Only",
          model: shortModelName(settings.model_name),
          stt: fileNameFromPath(settings.whisper_model_path),
          session: sessionId ? sessionId.slice(0, 8) : "booting",
          client: `${window.jarvisDesktop?.platform || "web"} · Electron ${window.jarvisDesktop?.versions.electron || "-"}`
        }}
      >
        <div className="app-workspace">
          <AppFeedback connection={connection} failures={failures} onDismiss={dismissFailure} />
          <div className="active-view">
            {activeTab === "chat" ? renderChatTab() : null}
            {activeTab === "approvals" ? renderApprovalsTab() : null}
            {activeTab === "settings" ? renderSettingsTab() : null}
            {activeTab === "smarthome" ? renderSmartHomeTab() : null}
          </div>
        </div>
      </AppShell>

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
    </>
  );
}

export default App;
