import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
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

const SILENCE_TIMEOUT_MS = 700;
const MIN_SEGMENT_MS = 450;
const MAX_SEGMENT_MS = 16000;
const VOICE_ACTIVITY_THRESHOLD = 0.018;
const WS_RECONNECT_BASE_MS = 350;
const WS_RECONNECT_MAX_MS = 5000;
const TTS_INPUT_SUPPRESSION_PREPLAY_MS = 350;
const TTS_INPUT_SUPPRESSION_POSTPLAY_MS = 140;
const RUN_COMPLETION_TIMEOUT_MS = 45_000;
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

  const busyRef = useRef(false);
  const voiceRepliesEnabledRef = useRef(true);
  const ttsPlaybackActiveRef = useRef(false);
  const suppressVoiceInputUntilRef = useRef(0);
  const lastAssistantSpokenTextRef = useRef("");

  const voiceQueueRef = useRef<string[]>([]);
  const voiceFlushRunningRef = useRef(false);

  const voiceModeEnabledRef = useRef(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mediaChunksRef = useRef<Blob[]>([]);

  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const analyserDataRef = useRef<Uint8Array | null>(null);
  const monitorRafRef = useRef<number | null>(null);

  const segmentStartAtRef = useRef(0);
  const lastSpeechAtRef = useRef(0);
  const speechDetectedInSegmentRef = useRef(false);
  const busyWatchdogTimerRef = useRef<number | null>(null);

  const sortedMessages = useMemo(() => {
    return [...messages].sort((a, b) => a.id - b.id);
  }, [messages]);

  const draftMessages = useMemo(() => {
    return Object.entries(draftByRun).map(([runId, content]) => ({ runId, content }));
  }, [draftByRun]);

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

  async function speakWithEchoGuard(text: string) {
    ttsPlaybackActiveRef.current = true;
    suppressVoiceInputFor(TTS_INPUT_SUPPRESSION_PREPLAY_MS);

    if (voiceModeEnabledRef.current && mediaRecorderRef.current?.state === "recording") {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
    }

    try {
      await speak(text);
    } finally {
      ttsPlaybackActiveRef.current = false;
      suppressVoiceInputFor(TTS_INPUT_SUPPRESSION_POSTPLAY_MS);
      resumeRecorderAfterSuppression();
    }
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

      if (rms >= VOICE_ACTIVITY_THRESHOLD) {
        speechDetectedInSegmentRef.current = true;
        lastSpeechAtRef.current = now;
      }

      const elapsed = now - segmentStartAtRef.current;
      const silenceElapsed = now - lastSpeechAtRef.current;

      const shouldCutBySilence =
        speechDetectedInSegmentRef.current &&
        silenceElapsed >= SILENCE_TIMEOUT_MS &&
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

  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);

  useEffect(() => {
    voiceRepliesEnabledRef.current = voiceRepliesEnabled;
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
      stopVoiceModeInternal({ updateStatus: false });
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
          setDraftByRun((previous) => ({
            ...previous,
            [payload.run_id]: `${previous[payload.run_id] || ""}${payload.token}`
          }));
          return;
        }

        if (payload.event === "message") {
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
            lastAssistantSpokenTextRef.current = payload.content;
            if (voiceRepliesEnabledRef.current) {
              void speakWithEchoGuard(payload.content).catch((error) => {
                setStatus((error as Error).message);
              });
            }
          }
          return;
        }

        if (payload.event === "run_state") {
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
    return (
      <div className="chat-grid">
        <section className="panel">
          <header className="panel-header">
            <h2>Konversation</h2>
            <p>{status}</p>
          </header>

          <div className="messages">
            {sortedMessages.map((message) => (
              <article key={message.id} className={`message ${message.role}`}>
                <header>
                  <span>{message.role === "assistant" ? "Jarvis" : "Du"}</span>
                  <time>{new Date(message.created_at).toLocaleTimeString()}</time>
                </header>
                <p>{message.content}</p>
                {message.role === "assistant" ? (
                  <button
                    className="tiny"
                    onClick={() => {
                      lastAssistantSpokenTextRef.current = message.content;
                      void speakWithEchoGuard(message.content).catch((error) => {
                        setStatus((error as Error).message);
                      });
                    }}
                  >
                    Vorlesen
                  </button>
                ) : null}
              </article>
            ))}

            {draftMessages.map((draft) => (
              <article key={draft.runId} className="message assistant draft">
                <header>
                  <span>Jarvis</span>
                  <time>stream</time>
                </header>
                <p>{draft.content || "..."}</p>
              </article>
            ))}
          </div>

          <form className="composer" onSubmit={onSubmit}>
            <textarea
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
            {timeline.map((item) => (
              <li key={item.id}>
                <div>
                  <strong>{item.state}</strong>
                  <span>{item.runId.slice(0, 8)}</span>
                </div>
                <p>{item.detail || "-"}</p>
                <time>{new Date(item.timestamp).toLocaleTimeString()}</time>
              </li>
            ))}
            {!timeline.length ? <li className="empty">Noch keine Aktivität</li> : null}
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
      </section>
    );
  }

  return (
    <main>
      <header className="app-header">
        <div>
          <h1>Jarvis Local v1</h1>
          <p>Cloudfrei auf diesem Mac mit lokalem Agent.</p>
        </div>
        <div className="env-pill">
          {window.jarvisDesktop?.platform || "web"} · Electron {window.jarvisDesktop?.versions.electron || "-"}
        </div>
      </header>

      <nav className="tabs">
        <button className={activeTab === "chat" ? "active" : ""} onClick={() => setActiveTab("chat")}>Chat</button>
        <button className={activeTab === "approvals" ? "active" : ""} onClick={() => setActiveTab("approvals")}>Approvals</button>
        <button className={activeTab === "settings" ? "active" : ""} onClick={() => setActiveTab("settings")}>Settings</button>
        <button className={activeTab === "smarthome" ? "active" : ""} onClick={() => setActiveTab("smarthome")}>Smart Home</button>
      </nav>

      {activeTab === "chat" ? renderChatTab() : null}
      {activeTab === "approvals" ? renderApprovalsTab() : null}
      {activeTab === "settings" ? renderSettingsTab() : null}
      {activeTab === "smarthome" ? renderSmartHomeTab() : null}
    </main>
  );
}

export default App;
