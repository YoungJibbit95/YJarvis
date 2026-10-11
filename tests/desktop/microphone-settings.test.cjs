const assert = require("node:assert/strict");
const { test } = require("node:test");
const React = require("react");
const { load } = require("./load-setup.cjs");

const micUtils = load("../voice/microphoneDevices.ts");

function nodes(node) {
  if (Array.isArray(node)) return node.flatMap(nodes);
  if (!node || typeof node !== "object") return [];
  return [node, ...nodes(node.props?.children)];
}

function readableText(node) {
  if (Array.isArray(node)) return node.map(readableText).join("");
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!node || typeof node !== "object") return "";
  return readableText(node.props?.children);
}

async function rig({ selectedId = "", sttAvailable = false, level = 175,
  getUserMediaError = null, recorderError = false, emptyBlob = false, recorderMime = "audio/webm" } = {}) {
  const slots = [], effects = [], recorders = [], tracks = [], contexts = [], calls = [], transcripts = [];
  const listeners = new Map(), timers = new Map();
  let cursor = 0, dirty = true, tree, timerId = 0, devices = [
    { kind: "audioinput", deviceId: "mic-1", label: "Built-in Mic" },
    { kind: "audioinput", deviceId: "mic-2", label: "USB Mic" },
    { kind: "videoinput", deviceId: "camera", label: "Camera" }
  ];
  let deviceDisconnected = 0;
  const ReactMock = {
    ...React,
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial;
      return [slots[index], value => {
        const next = typeof value === "function" ? value(slots[index]) : value;
        if (!Object.is(slots[index], next)) { slots[index] = next; dirty = true; }
      }];
    },
    useRef(value) {
      const i = cursor++;
      return slots[i] ??= { current: value };
    },
    useCallback(fn, deps) {
      const index = cursor++, previous = slots[index];
      if (previous && deps.every((dep, i) => Object.is(dep, previous.deps[i]))) {
        return previous.fn;
      }
      slots[index] = { fn, deps };
      return fn;
    },
    useEffect(fn, deps) {
      const index = cursor++, previous = slots[index];
      if (!previous || deps.some((dep, i) => !Object.is(dep, previous.deps[i]))) {
        slots[index] = { deps, cleanup: previous?.cleanup };
        effects.push(() => { slots[index].cleanup?.(); slots[index].cleanup = fn(); });
      }
    }
  };
  class Recorder {
    state = "inactive";
    mimeType = recorderMime;
    constructor(stream) { recorders.push(this); }
    start() {
      if (recorderError) throw new Error("MediaRecorder.start failed");
      this.state = "recording";
    }
    stop() {
      this.state = "inactive";
      this.ondataavailable?.({ data: new Blob([emptyBlob ? "" : "test audio"], { type: "audio/webm" }) });
      this.onstop?.();
    }
  }
  class Context {
    constructor() { contexts.push(this); }
    createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
    createAnalyser() { return { fftSize: 2048, getByteTimeDomainData(samples) { samples.fill(level); } }; }
    async resume() {}
    async close() { this.closed = true; }
  }
  const track = { enabled: true, readyState: "live", stopped: false, stop() { this.stopped = true; } };
  const stream = { getAudioTracks: () => [track], getTracks: () => [track] };
  tracks.push(track);
  const media = {
    async enumerateDevices() { return devices; },
    async getUserMedia(constraints) {
      calls.push(JSON.parse(JSON.stringify(constraints)));
      if (getUserMediaError) throw getUserMediaError;
      return stream;
    },
    addEventListener(name, fn) { listeners.set(name, fn); },
    removeEventListener(name) { listeners.delete(name); }
  };
  const window = {
    AudioContext: Context, jarvisDesktop: {
      platform: "win32", microphoneStatus: async () => "not-determined",
      openMicrophonePrivacySettings: async () => true
    },
    setInterval(callback) { const id = ++timerId; timers.set(id, callback); return id; },
    clearInterval(id) { timers.delete(id); }
  };
  const api = {
    async transcribe(blob) {
      transcripts.push(blob);
      return { text: "Test erkannt", latency_ms: 45, language: "de" };
    }
  };
  const { MicrophoneSettings } = load("../voice/MicrophoneSettings.tsx", {
    react: ReactMock, "../api": api, "./microphoneDevices": micUtils,
  }, { window, navigator: { mediaDevices: media }, MediaRecorder: Recorder, Blob, Error });

  const props = { selectedId, sttAvailable, voiceActive: false,
    onSelect(id) { props.selectedId = id; dirty = true; },
    onDeviceUnavailable() { deviceDisconnected++; }
  };

  async function settle() {
    for (let iteration = 0; iteration < 30; iteration++) {
      await Promise.resolve();
      if (dirty) {
        dirty = false; cursor = 0;
        tree = MicrophoneSettings(props);
        effects.splice(0).forEach(run => run());
      }
    }
  }
  function button(name) {
    const found = nodes(tree).find(n => n.type === "button" &&
      nodes(n.props.children).some(child => typeof child === "string" && child.includes(name)));
    // JSX strings are primitive and not part of nodes(). For button children,
    // flatten separately; this deliberately exercises the actual onClick callback.
    const buttons = nodes(tree).filter(n => n.type === "button");
    const match = buttons.find(n => JSON.stringify(n.props.children).includes(name));
    return found || match;
  }
  function status() { return JSON.stringify(tree); }
  await settle();
  return {
    props, tracks, recorders, contexts, calls, transcripts, timers, listeners, settle, button, status,
    tick() { for (const fn of timers.values()) fn(); },
    devices(next) { devices = next; listeners.get("devicechange")?.(); },
    disconnected: () => deviceDisconnected,
    visibleText: () => readableText(tree),
    unmount() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}

test("microphone hardware test is available without Whisper and never submits chat", async () => {
  const h = await rig({ sttAvailable: false, selectedId: "mic-2" });
  assert.ok(h.button("Mikrofon testen"));
  assert.ok(h.button("Spracherkennung testen"));
  h.button("Mikrofon testen").props.onClick();
  await h.settle();
  assert.equal(h.recorders.length, 1);
  assert.equal(h.calls[0].audio.deviceId.exact, "mic-2");
  h.tick(); await h.settle();
  assert.match(h.status(), /Signal erkannt/);
  h.button("Test beenden").props.onClick();
  await h.settle();
  assert.match(h.status(), /nicht-leerer MediaRecorder-Blob/);
  assert.equal(h.transcripts.length, 0);
  assert.equal(h.tracks[0].stopped, true);
  assert.equal(h.contexts[0].closed, true);
  assert.equal(h.timers.size, 0);
});

test("Whisper test transcribes locally but does not send a chat request", async () => {
  const h = await rig({ sttAvailable: true });
  h.button("Spracherkennung testen").props.onClick(); await h.settle();
  h.tick(); await h.settle();
  h.button("Test beenden").props.onClick(); await h.settle();
  assert.equal(h.transcripts.length, 1);
  assert.match(h.status(), /Test erkannt/);
  assert.match(h.visibleText(), /Whisper-Latenz: 45 ms/);
  assert.equal(h.tracks[0].stopped, true);
});

test("permission rejection and missing devices have distinct actionable states", async () => {
  const error = new Error("denied"); error.name = "NotAllowedError";
  const h = await rig({ getUserMediaError: error });
  h.button("Mikrofon testen").props.onClick(); await h.settle();
  assert.match(h.status(), /Windows 11/);
  assert.equal(h.recorders.length, 0);
  h.devices([{ kind: "videoinput", deviceId: "webcam", label: "Camera" }]); await h.settle();
  assert.match(h.status(), /Keine benannten Audio-Eingänge/);
});

test("devicechange on selected missing USB microphone reports instead of falling back", async () => {
  const h = await rig({ selectedId: "mic-2" });
  h.devices([{ kind: "audioinput", deviceId: "mic-1", label: "Built-in Mic" }]); await h.settle();
  assert.equal(h.disconnected(), 1);
  assert.match(h.status(), /kein automatischer Wechsel/);
  assert.equal(h.props.selectedId, "mic-2");
});

test("no signal and empty blobs are not treated as successful hardware tests", async () => {
  for (const opts of [{ level: 128 }, { emptyBlob: true }]) {
    const h = await rig(opts);
    h.button("Mikrofon testen").props.onClick(); await h.settle();
    h.tick(); await h.settle();
    h.button("Test beenden").props.onClick(); await h.settle();
    assert.match(h.status(), /kein relevantes Mikrofon-Signal|keine verwertbaren Audio-Daten/);
    assert.equal(h.transcripts.length, 0);
  }
});

test("stop/unmount releases tracks and never permits simultaneous recorders", async () => {
  const h = await rig();
  h.button("Mikrofon testen").props.onClick(); await h.settle();
  assert.equal(h.recorders.length, 1);
  assert.equal(h.button("Mikrofon testen"), undefined);
  h.unmount();
  assert.equal(h.tracks[0].stopped, true);
  assert.equal(h.timers.size, 0);
});


test("explicit permission request releases capture immediately without Recorder or Whisper", async () => {
  const h = await rig({ sttAvailable: false, selectedId: "mic-2" });
  assert.match(h.status(), /Noch nicht angefragt/);
  h.button("Mikrofonzugriff anfordern").props.onClick();
  await h.settle();
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].audio.deviceId.exact, "mic-2");
  assert.equal(h.calls[0].video, false);
  assert.equal(h.tracks[0].stopped, true);
  assert.equal(h.recorders.length, 0);
  assert.equal(h.transcripts.length, 0);
  assert.match(h.visibleText(), /Mikrofon erfolgreich geöffnet/);
});

test("native OS recovery is explicit and never claims hardware access from status alone", async () => {
  const h = await rig({ sttAvailable: false });
  assert.match(h.visibleText(), /Noch nicht angefragt/);
  h.button("Betriebssystem-Einstellungen öffnen").props.onClick();
  await h.settle();
  assert.match(h.visibleText(), /Systemeinstellungen geöffnet/);
  h.button("Berechtigung erneut prüfen").props.onClick();
  await h.settle();
  assert.equal(h.calls.length, 0, "read-only recheck must never start a microphone");
});

test("MediaRecorder.start failure closes context/tracks and allows retry", async () => {
  const h = await rig({ recorderError: true });
  h.button("Mikrofon testen").props.onClick();
  await h.settle();
  assert.match(h.visibleText(), /MediaRecorder.start failed/);
  assert.equal(h.tracks[0].stopped, true);
  assert.equal(h.contexts[0].closed, true);
  assert.equal(h.timers.size, 0);
});

test("Whisper rejects unsupported recorder MIME without submitting chat", async () => {
  const h = await rig({ sttAvailable: true, recorderMime: "application/octet-stream" });
  h.button("Spracherkennung testen").props.onClick();
  await h.settle();
  h.tick(); await h.settle();
  h.button("Test beenden").props.onClick(); await h.settle();
  assert.match(h.visibleText(), /nicht als kompatibel bestätigt/);
  assert.equal(h.transcripts.length, 0);
});
