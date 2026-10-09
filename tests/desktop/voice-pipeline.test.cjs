const assert = require("node:assert/strict");
const { test } = require("node:test");
const React = require("react");
const { load } = require("./load-setup.cjs");
const voice = load("../voice/voiceReliability.ts");
const microphone = load("../voice/microphoneDevices.ts");

function nodes(node) {
  if (!node || typeof node !== "object") return [];
  if (Array.isArray(node)) return node.flatMap(nodes);
  return [node, ...nodes(node.props?.children)];
}

// Executes the actual App callbacks with in-memory MediaRecorder and Whisper/Chat.
// No real microphone, audio data, network, model or recordings touch the filesystem.
async function makeHarness(overrides = {}) {
  let cursor = 0, dirty = true, tree, timerSeq = 0, clock = 1000;
  let level = 128, rejectResume = false, confirmedRetry = false;
  let setupCheck = { state: "degraded", backendReachable: true };
  const slots = [], effects = [], timers = new Map(), frames = [], recorders = [], tracks = [], sends = [], transcriptions = [], sockets = [];
  const mockReact = {
    ...React, memo: (component) => component,
    useState(init) {
      const id = cursor++;
      if (!(id in slots)) slots[id] = typeof init === "function" ? init() : init;
      return [slots[id], (value) => {
        const next = typeof value === "function" ? value(slots[id]) : value;
        if (!Object.is(next, slots[id])) { slots[id] = next; dirty = true; }
      }];
    },
    useRef(value) { return slots[cursor++] ??= { current: value }; },
    useMemo: (fn) => fn(), useCallback: (fn) => fn,
    useDeferredValue: (val) => val, useTransition: () => [false, (fn) => fn()],
    useEffect(callback, deps) {
      const id = cursor++, prev = slots[id];
      if (!prev || deps.some((v, i) => !Object.is(v, prev.deps[i]))) {
        slots[id] = { deps, cleanup: prev?.cleanup };
        effects.push(() => { slots[id].cleanup?.(); slots[id].cleanup = callback(); });
      }
    }
  };
  class Clock extends Date {
    constructor(...args) { super(...(args.length ? args : [clock])); }
    static now() { return clock; }
  }
  class Recorder {
    static isTypeSupported(type) { return type.startsWith("audio/webm"); }
    constructor(stream, options) {
      this.state = "inactive";
      this.mimeType = options.mimeType || "audio/webm";
      this.payload = "";
      recorders.push(this);
    }
    start(timeslice) { assert.equal(timeslice, 1000); this.state = "recording"; }
    stop() {
      assert.equal(this.state, "recording");
      this.state = "inactive";
      // The stop request happens BEFORE the final ondataavailable event.
      queueMicrotask(() => {
        this.ondataavailable?.({ data: new Blob([this.payload], { type: this.mimeType }) });
        this.onstop?.();
      });
    }
  }
  class Context {
    createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
    createAnalyser() {
      return { fftSize: 2048, getByteTimeDomainData(data) { data.fill(level); } };
    }
    async resume() { if (rejectResume) throw new Error("AudioContext resume rejected"); }
    async close() {}
  }
  class Socket {
    static OPEN = 1; static CONNECTING = 0;
    readyState = 0;
    constructor(url) { this.url = url; sockets.push(this); }
    close() { this.readyState = 3; }
    open() { this.readyState = 1; this.onopen?.(); }
    disconnect() { this.readyState = 3; this.onclose?.(); }
    event(payload) { this.onmessage?.({ data: JSON.stringify(payload) }); }
  }
  const stream = { getTracks: () => tracks };
  tracks.push({ stopped: false, stop() { this.stopped = true; } });
  const api = {
    createSession: async () => ({ session_id: "voice-session" }),
    fetchMessages: async () => [], fetchApprovals: async () => [],
    fetchSettings: async () => ({
      model_name: "fixture", language: "de", ollama_base_url: "http://fixture",
      tts_engine: "piper", tts_voice: "", tts_model_path: "", whisper_binary: "auto",
      whisper_model_path: "", say_rate_wpm: 235, tts_sir_pronunciation: "Sör", allowed_paths: []
    }),
    fetchSmartHomeEntities: async () => [], fetchAudioVoices: async () => [],
    transcribe: async (blob) => {
      transcriptions.push(blob);
      return { text: await blob.text(), language: "de", latency_ms: 18 };
    },
    sendChat: async (id, message) => {
      sends.push({ id, message });
      return { run_id: "run-" + sends.length };
    },
    speak: async () => ({ ok: true }),
    wsUrl: () => "ws://fixture",
    ChatSubmissionError: class ChatSubmissionError extends Error {
      constructor(message, outcome) { super(message); this.outcome = outcome; }
    },
    ...overrides
  };
  const window = {
    AudioContext: Context, confirm() { return confirmedRetry; },
    addEventListener() {}, removeEventListener() {},
    setTimeout(fn, duration) { const id = ++timerSeq; timers.set(id, { fn, duration }); return id; },
    clearTimeout(id) { timers.delete(id); }, cancelAnimationFrame() {}
  };
  const { default: App } = load("../App.tsx", {
    react: mockReact, "./api": api, "./voice/voiceReliability": voice,
    "./app/AppShell": { AppShell: () => null },
    "./app/AppFeedback": { AppFeedback: () => null },
    "./app/PresenceStage": { PresenceStage: () => null, runStateLabel: () => "event" },
    "./app/ActionReview": { ActionReview: () => null },
    "./setup/SetupStatusView": { SetupNotice: () => null },
    "./setup/GuidedInstaller": { GuidedInstaller: () => null },
    "./components/IntelligentSettings": { IntelligentSettings: () => null },
    "./voice/microphoneDevices": microphone
  }, {
    Date: Clock, Blob, Error, MediaRecorder: Recorder, WebSocket: Socket,
    Math: Object.assign(Object.create(Math), { random: () => 0.42 }),
    window, navigator: { mediaDevices: { getUserMedia: async () => stream } },
    requestAnimationFrame(fn) { frames.push(fn); return frames.length; },
    cancelAnimationFrame() {}
  });
  async function settle() {
    for (let round = 0; round < 3; round++) {
      for (let i = 0; i < 30; i++) {
        await Promise.resolve();
        if (dirty) {
          dirty = false; cursor = 0;
          tree = App({ setupCheck, onRecheckSetup: async () => {} });
          effects.splice(0).forEach((run) => run());
        }
      }
      // Node Blob.text() and simulated recorder callbacks may need an event-loop turn.
      await new Promise((resolve) => setImmediate(resolve));
    }
  }
  const find = (predicate) => nodes(tree).find(predicate);
  await settle();
  const recordButton = () => find((node) => node.type === "button" &&
    typeof node.props?.className === "string" && node.props.className.includes("record"));
  return {
    sends, transcriptions, recorders, tracks, sockets, api, find, settle,
    socket() { return sockets.at(-1); },
    async openSocket() { this.socket().open(); await settle(); },
    async closeSocket() { this.socket().disconnect(); await settle(); },
    async socketEvent(event, run_id, state, content = "") {
      this.socket().event(event === "run_state"
        ? { event, run_id, state, timestamp: new Date(clock).toISOString() }
        : { event, run_id, role: "assistant", content, timestamp: new Date(clock).toISOString() });
      await settle();
    },
    hasTimer(duration) { return [...timers.values()].some((t) => t.duration === duration); },
    clock() { return clock; },
    async start() { recordButton().props.onClick(); await settle(); },
    async stop() { recordButton().props.onClick(); await settle(); },
    async finish(payload, options = {}) {
      const recorder = recorders.at(-1);
      recorder.payload = payload;
      if (options.voice !== false) this.frame(60, 160);
      recorder.stop();
      await settle();
    },
    frame(ms = 50, sample = 128) {
      level = sample; clock += ms;
      const fn = frames.shift();
      if (fn) fn();
    },
    async timer(duration) {
      const found = [...timers].find(([, entry]) => entry.duration === duration);
      assert.ok(found, "expected timeout " + duration);
      timers.delete(found[0]); found[1].fn();
      await settle();
    },
    setClock(ms) { clock = ms; },
    advance(ms) { clock += ms; },
    async setup(state) { setupCheck = { state, backendReachable: state !== "checking" }; dirty = true; await settle(); },
    setConfirmedRetry(value) { confirmedRetry = value; },
    setResumeFailure() { rejectResume = true; },
    visible() { return nodes(tree).filter((node) => node.type === "p" || node.type === "li")
      .map((node) => JSON.stringify(node.props?.children)).join(" "); },
    queueCards() { return nodes(tree).filter((node) => node.props?.className === "voice-reliability-panel"); }
  };
}

test("real App: wakeword and follow-up across MediaRecorder segments submit once", async () => {
  const app = await makeHarness();
  await app.start();
  await app.finish("Jarvis");
  assert.equal(app.sends.length, 0);
  await app.timer(80);
  assert.equal(app.recorders.length, 2);
  await app.finish("Öffne Spotify");
  assert.equal(app.transcriptions.length, 2);
  assert.deepEqual(app.sends.map((entry) => entry.message), ["Öffne Spotify"]);
  assert.match(app.visible(), /Öffne Spotify/);
});

test("real App: combined command is finalized on manual stop after capture", async () => {
  const app = await makeHarness();
  await app.start();
  app.recorders[0].payload = "Jarvis, öffne Spotify";
  app.frame(60, 160);
  await app.stop();
  assert.equal(app.tracks[0].stopped, true);
  assert.deepEqual(app.sends.map((entry) => entry.message), ["öffne Spotify"]);
  assert.match(app.visible(), /Letztes Transkript/);
});

test("real App: no wakeword cannot submit; preview Whisper requests are absent", async () => {
  const app = await makeHarness();
  await app.start();
  await app.finish("Öffne Spotify");
  assert.equal(app.sends.length, 0);
  assert.equal(app.transcriptions.length, 1);
});

test("real App: manual stop during unresolved Whisper still submits valid command", async () => {
  let resolveTranscribe;
  const app = await makeHarness({
    transcribe: () => new Promise((resolve) => { resolveTranscribe = resolve; })
  });
  await app.start();
  app.recorders[0].payload = "Jarvis, öffne Spotify";
  app.frame(60, 160);
  await app.stop();
  assert.equal(app.sends.length, 0);
  resolveTranscribe({ text: "Jarvis, öffne Spotify", language: "de", latency_ms: 42 });
  await app.settle();
  assert.deepEqual(app.sends.map((entry) => entry.message), ["öffne Spotify"]);
});

test("real App: uncertain chat acknowledgement is pending without retry storm", async () => {
  let count = 0;
  const Err = class ChatSubmissionError extends Error {
    constructor(message, outcome) { super(message); this.outcome = outcome; }
  };
  const app = await makeHarness({
    ChatSubmissionError: Err,
    sendChat: async () => { count++; throw new Err("ack lost", "unknown"); }
  });
  await app.start();
  await app.finish("Jarvis, öffne Spotify");
  await app.settle();
  assert.equal(count, 1);
  await app.settle();
  assert.equal(count, 1);
  assert.match(app.visible(), /Ausgang unklar/);
  const retry = app.find((node) => node.type === "button" && node.props?.children === "Erneut senden");
  retry.props.onClick();
  await app.settle();
  assert.equal(count, 1); // User declined risky duplicate action.
  app.setConfirmedRetry(true);
  retry.props.onClick();
  await app.settle();
  assert.equal(count, 2); // Only explicitly acknowledged user retry.
});

test("real App: pending transcript persists through setup rechecks and sends when ready", async () => {
  const app = await makeHarness();
  await app.start();
  app.recorders[0].payload = "Jarvis, öffne Spotify";
  app.frame(60, 160);
  await app.setup("checking");
  assert.equal(app.sends.length, 0);
  assert.match(app.visible(), /Wartet auf Chat-Verfügbarkeit/);
  await app.setup("degraded");
  assert.deepEqual(app.sends.map((entry) => entry.message), ["öffne Spotify"]);
});

test("real App: AudioContext failure releases all microphone tracks", async () => {
  const app = await makeHarness();
  app.setResumeFailure();
  await app.start();
  assert.equal(app.tracks[0].stopped, true);
  assert.equal(app.recorders.length, 0);
});


test("HIGH: stop/restart requires a fresh wakeword before accepting a command", async () => {
  const app = await makeHarness();
  await app.start();
  await app.finish("Jarvis");
  await app.stop();
  await app.start();
  await app.finish("Öffne Spotify");
  assert.deepEqual(app.sends, []);
  assert.match(app.visible(), /Ohne Wakeword ignoriert/);
  await app.timer(80);
  await app.finish("Jarvis, öffne Spotify");
  assert.deepEqual(app.sends.map((entry) => entry.message), ["öffne Spotify"]);
});

test("HIGH: captured follow-up completes exactly once after manual Stop during Whisper", async () => {
  let resolveFollowup;
  const app = await makeHarness({
    transcribe: async (blob) => {
      const text = await blob.text();
      if (text === "Öffne Spotify") {
        return await new Promise((resolve) => { resolveFollowup = resolve; });
      }
      return { text, language: "de", latency_ms: 7 };
    }
  });
  await app.start();
  await app.finish("Jarvis");
  await app.timer(80);
  app.recorders.at(-1).payload = "Öffne Spotify";
  app.frame(60, 160);
  await app.stop();
  assert.equal(app.sends.length, 0);
  resolveFollowup({ text: "Öffne Spotify", language: "de", latency_ms: 30 });
  await app.settle();
  assert.deepEqual(app.sends.map((entry) => entry.message), ["Öffne Spotify"]);
  await app.settle();
  assert.equal(app.sends.length, 1);
});

test("HIGH: old delayed wake STT cannot arm a restarted capture activation", async () => {
  let resolveOld;
  let first = true;
  const app = await makeHarness({
    transcribe: async (blob) => {
      const text = await blob.text();
      if (first) {
        first = false;
        return await new Promise((resolve) => { resolveOld = resolve; });
      }
      return { text, language: "de", latency_ms: 7 };
    }
  });
  await app.start();
  await app.finish("Jarvis");
  await app.stop();
  await app.start();
  await app.finish("Öffne Spotify");
  resolveOld({ text: "Jarvis", language: "de", latency_ms: 800 });
  await app.settle();
  await app.timer(80);
  await app.finish("Öffne Notizen");
  assert.deepEqual(app.sends, []);
});

test("MEDIUM: WebSocket disconnect pauses accepted voice Run; reconnect is not completion", async () => {
  const app = await makeHarness();
  await app.openSocket();
  await app.start();
  await app.finish("Jarvis, öffne Spotify");
  assert.equal(app.sends.length, 1);
  await app.closeSocket();
  await app.timer(80);
  await app.finish("Jarvis, öffne Notizen");
  assert.equal(app.sends.length, 1);
  assert.match(app.visible(), /Warteschlange|Nachfolgende Befehle/);
  await app.timer(350);
  await app.openSocket();
  assert.equal(app.sends.length, 1);
  await app.socketEvent("run_state", "unrelated-run", "done");
  assert.equal(app.sends.length, 1);
  await app.socketEvent("run_state", "run-1", "done");
  assert.deepEqual(app.sends.map((entry) => entry.message),
    ["öffne Spotify", "öffne Notizen"]);
});

test("MEDIUM: foreign/late terminal events never unlock the active voice submission", async () => {
  const app = await makeHarness();
  await app.openSocket();
  await app.start();
  await app.finish("Jarvis, öffne Spotify");
  await app.timer(80);
  await app.finish("Jarvis, öffne Notizen");
  await app.socketEvent("run_state", "run-from-past-session", "done");
  assert.equal(app.sends.length, 1);
  await app.socketEvent("run_state", "run-1", "done");
  assert.equal(app.sends.length, 2);
  await app.socketEvent("run_state", "run-1", "done");
  await app.socketEvent("run_state", "unrelated-run", "error");
  assert.equal(app.sends.length, 2);
  assert.equal(app.hasTimer(45_000), true); // Second run must still own its watchdog.
});

test("MEDIUM: run_state done before HTTP acknowledgement does not start a stale watchdog", async () => {
  let resolveAck;
  const posts = [];
  const app = await makeHarness({
    sendChat: async (_session, message) => {
      posts.push(message);
      return await new Promise((resolve) => { resolveAck = resolve; });
    }
  });
  await app.openSocket();
  await app.start();
  await app.finish("Jarvis, öffne Spotify");
  assert.deepEqual(posts, ["öffne Spotify"]);
  await app.socketEvent("run_state", "fast-run", "done");
  resolveAck({ run_id: "fast-run" });
  await app.settle();
  assert.equal(app.hasTimer(45_000), false);
  await app.timer(80);
  await app.finish("Jarvis, öffne Notizen");
  assert.deepEqual(posts, ["öffne Spotify", "öffne Notizen"]);
});

test("MEDIUM: run_state error before HTTP acknowledgement does not produce false timeout", async () => {
  let resolveAck;
  const app = await makeHarness({
    sendChat: async () => await new Promise((resolve) => { resolveAck = resolve; })
  });
  await app.openSocket();
  await app.start();
  await app.finish("Jarvis, öffne Spotify");
  await app.socketEvent("run_state", "fast-failed-run", "error");
  resolveAck({ run_id: "fast-failed-run" });
  await app.settle();
  assert.equal(app.hasTimer(45_000), false);
  assert.match(app.visible(), /Run fehlgeschlagen|Vom Agent angenommen/);
});

test("MEDIUM: wrong early terminal ID cannot complete a different acknowledged Run", async () => {
  let resolveAck;
  const app = await makeHarness({
    sendChat: async () => await new Promise((resolve) => { resolveAck = resolve; })
  });
  await app.openSocket();
  await app.start();
  await app.finish("Jarvis, öffne Spotify");
  await app.socketEvent("run_state", "other-run", "done");
  resolveAck({ run_id: "my-run" });
  await app.settle();
  assert.equal(app.hasTimer(45_000), true);
  await app.socketEvent("run_state", "my-run", "done");
  assert.equal(app.hasTimer(45_000), false);
});

test("MEDIUM: explicit decision releases an uncertain Run, never implicitly", async () => {
  const app = await makeHarness();
  await app.openSocket();
  await app.start();
  await app.finish("Jarvis, öffne Spotify");
  await app.timer(80);
  await app.finish("Jarvis, öffne Notizen");
  await app.closeSocket();
  const unblock = app.find((node) => node.type === "button" &&
    node.props?.children === "Run prüfen und bewusst fortsetzen");
  assert.ok(unblock);
  unblock.props.onClick();
  await app.settle();
  assert.equal(app.sends.length, 1);
  app.setConfirmedRetry(true);
  unblock.props.onClick();
  await app.settle();
  assert.equal(app.sends.length, 2);
});

test("LOW: identical capture timestamps and fixed random values preserve distinct voice messages", async () => {
  const app = await makeHarness();
  await app.start();
  await app.finish("Jarvis, erste Aufgabe");
  const sameTime = app.clock();
  await app.socketEvent("run_state", "run-1", "done");
  await app.timer(80);
  app.setClock(sameTime - 60);
  await app.finish("Jarvis, zweite Aufgabe");
  assert.deepEqual(app.sends.map((entry) => entry.message), ["erste Aufgabe", "zweite Aufgabe"]);
  assert.match(app.visible(), /erste Aufgabe/);
  assert.match(app.visible(), /zweite Aufgabe/);
});

test("TTS echo: fully captured command before new assistant playback stays valid", async () => {
  let finishStt;
  const app = await makeHarness({
    transcribe: async () => await new Promise((resolve) => { finishStt = resolve; })
  });
  await app.openSocket();
  await app.start();
  app.recorders[0].payload = "Jarvis, öffne Spotify";
  app.frame(60, 160);
  await app.stop();
  await app.socketEvent("message", "other-run", null, "Jarvis, öffne Spotify");
  finishStt({ text: "Jarvis, öffne Spotify", language: "de", latency_ms: 500 });
  await app.settle();
  assert.deepEqual(app.sends.map((entry) => entry.message), ["öffne Spotify"]);
});

test("TTS echo: assistant playback starting during an open capture flushes valid prior audio", async () => {
  const app = await makeHarness();
  await app.openSocket();
  await app.start();
  app.recorders[0].payload = "Jarvis, öffne Spotify";
  app.frame(60, 160);
  await app.socketEvent("message", "assistant-run", null, "Eine andere Antwort.");
  assert.deepEqual(app.sends.map((entry) => entry.message), ["öffne Spotify"]);
});

test("TTS echo: overlapping assistant chunks do not overwrite the capture-time echo reference", async () => {
  const pending = [], played = [];
  const app = await makeHarness({
    speak: (text) => {
      played.push(text);
      return new Promise((resolve) => pending.push(resolve));
    }
  });
  await app.openSocket();
  await app.start();
  app.recorders[0].payload = "Jarvis, öffne Spotify";
  app.frame(60, 160);
  await app.socketEvent("message", "tts-1", null, "Jarvis, öffne Spotify");
  await app.socketEvent("message", "tts-2", null, "Jarvis, öffne Spotify erneut");
  assert.equal(played.length, 1);
  assert.equal(app.sends.length, 1);
  pending.shift()({ ok: true });
  await app.settle();
  await app.timer(18); // Existing TTS queue schedules its next chunk separately.
  assert.equal(played.length, 2);
  pending.shift()({ ok: true });
  await app.settle();
  assert.equal(app.sends.length, 1);
});

test("TTS echo: short assistant 'Jarvis' must not open the wakeword window", async () => {
  const app = await makeHarness();
  await app.openSocket();
  await app.start();
  await app.socketEvent("message", "tts-short", null, "Jarvis");
  app.advance(500); // AFTER playback but still near the last assistant chunk.
  await app.timer(430); // existing TTS suppression + recorder-restart delay
  await app.finish("Jarvis");
  await app.timer(80);
  await app.finish("Öffne Spotify");
  assert.deepEqual(app.sends, []);
});
