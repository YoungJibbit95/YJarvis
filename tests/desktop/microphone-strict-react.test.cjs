const assert = require("node:assert/strict");
const { test } = require("node:test");
const React = require("react");
const { load } = require("./load-setup.cjs");

/**
 * Uses the actual react-dom/client createRoot + React.StrictMode lifecycle,
 * NOT the project's simplified mock useEffect hook driver.
 * A minimal inert DOM host is sufficient for React reconciliation under Node;
 * microphone/audio themselves remain simulated.
 */
function fakeDom() {
  let doc;
  class Node {
    constructor(name, type, value = "") {
      this.nodeType = type; this.nodeName = name;
      this.tagName = type === 1 ? name : undefined;
      this.nodeValue = type === 3 ? value : null;
      this.parentNode = null; this.childNodes = [];
      this.ownerDocument = doc; this.namespaceURI = "http://www.w3.org/1999/xhtml";
      this.style = { setProperty() {}, removeProperty() {} };
      this.attributes = {};
      this.selected = false;
      this.value = "";
    }
    get firstChild() { return this.childNodes[0] || null; }
    get lastChild() { return this.childNodes[this.childNodes.length - 1] || null; }
    get nextSibling() {
      if (!this.parentNode) return null;
      return this.parentNode.childNodes[this.parentNode.childNodes.indexOf(this) + 1] || null;
    }
    get textContent() {
      return this.nodeType === 3 ? this.nodeValue :
        this.childNodes.map(child => child.textContent || "").join("");
    }
    set textContent(text) {
      if (this.nodeType === 3) { this.nodeValue = String(text); return; }
      this.childNodes.forEach(item => { item.parentNode = null; });
      this.childNodes = [];
      if (text) this.appendChild(doc.createTextNode(String(text)));
    }
    get options() { return this.descendants().filter(item => item.tagName === "OPTION"); }
    descendants() { return this.childNodes.flatMap(node => [node, ...node.descendants()]); }
    appendChild(node) {
      if (node.parentNode) node.parentNode.removeChild(node);
      this.childNodes.push(node); node.parentNode = this; return node;
    }
    insertBefore(node, before) {
      if (!before) return this.appendChild(node);
      const index = this.childNodes.indexOf(before);
      if (index < 0) throw Error("missing sibling");
      if (node.parentNode) node.parentNode.removeChild(node);
      this.childNodes.splice(index, 0, node); node.parentNode = this; return node;
    }
    removeChild(node) {
      const index = this.childNodes.indexOf(node);
      if (index < 0) throw Error("not a child");
      this.childNodes.splice(index, 1); node.parentNode = null; return node;
    }
    contains(child) {
      return child === this || this.childNodes.some(node => node.contains(child));
    }
    addEventListener() {}
    removeEventListener() {}
    closest() { return null; }
    scrollTo() {}
    setAttribute(key, value) { this.attributes[key] = String(value); }
    removeAttribute(key) { delete this.attributes[key]; }
    getAttribute(key) { return this.attributes[key] ?? null; }
    hasAttribute(key) { return key in this.attributes; }
    focus() { doc.activeElement = this; }
  }
  doc = new Node("#document", 9);
  doc.ownerDocument = doc;
  doc.createElement = (name) => new Node(name.toUpperCase(), 1);
  doc.createElementNS = (_, name) => doc.createElement(name);
  doc.createTextNode = value => new Node("#text", 3, String(value));
  doc.createComment = value => new Node("#comment", 8, String(value));
  doc.documentElement = doc.createElement("html");
  doc.body = doc.createElement("body");
  doc.documentElement.appendChild(doc.body);
  doc.appendChild(doc.documentElement);
  doc.activeElement = doc.body;
  const win = {
    document: doc, HTMLElement: Node, HTMLIFrameElement: Node,
    Node, SVGElement: Node, getSelection: () => null,
    addEventListener() {}, removeEventListener() {},
    jarvisDesktop: { platform: "win32", microphoneStatus: async () => "unknown" },
  };
  doc.defaultView = win;
  return { doc, win, Node };
}

async function withMountedMicrophone(callback, { settingsView = false } = {}) {
  const { doc, win, Node } = fakeDom();
  // Node 22+ exposes navigator via a getter-only global. Define temporary
  // own properties and restore their *descriptors* (not just old values) even
  // if a React effect, media mock or assertion throws.
  const replacements = {
    window: win, document: doc, navigator: { userAgent: "node-react-strict-test" },
    HTMLElement: Node, Node, IS_REACT_ACT_ENVIRONMENT: true,
  };
  const originals = Object.fromEntries(
    Object.keys(replacements).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)])
  );
  originals.MediaRecorder = Object.getOwnPropertyDescriptor(globalThis, "MediaRecorder");
  try {
    for (const [key, value] of Object.entries(replacements)) {
      Object.defineProperty(globalThis, key, {
        value, configurable: true, writable: true, enumerable: true
      });
    }
    let root;
  const intervals = new Map(), requests = [], tracks = [], recorders = [], contexts = [];
  const mediaListeners = new Map();
  let intervalId = 0, setupCalls = 0, cleanups = 0;
  let nativeStatus = "unknown";
  win.jarvisDesktop.microphoneStatus = async () => nativeStatus;
  let devices = [{ kind: "audioinput", deviceId: "mic-usb", label: "USB Mic" }];
  const media = {
    async enumerateDevices() { return devices; },
    async getUserMedia(options) {
      requests.push(options);
      const track = { readyState: "live", enabled: true, stops: 0,
        stop() { this.stops++; this.readyState = "ended"; } };
      tracks.push(track);
      return { getAudioTracks: () => [track], getTracks: () => [track] };
    },
    addEventListener(name, listener) {
      setupCalls++;
      if (!mediaListeners.has(name)) mediaListeners.set(name, new Set());
      mediaListeners.get(name).add(listener);
    },
    removeEventListener(name, listener) {
      cleanups++; mediaListeners.get(name)?.delete(listener);
    },
  };
  const browserContext = class {
    constructor() { this.closed = 0; contexts.push(this); }
    createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
    createAnalyser() { return { fftSize: 2048, getByteTimeDomainData(bytes) { bytes.fill(190); } }; }
    async resume() {}
    async close() { this.closed++; }
  };
  win.AudioContext = browserContext;
  win.setInterval = fn => { const id = ++intervalId; intervals.set(id, fn); return id; };
  win.clearInterval = id => intervals.delete(id);
  win.setTimeout = fn => { const id = ++intervalId; intervals.set(id, fn); return id; };
  win.clearTimeout = id => intervals.delete(id);
  const Recorder = class {
    state = "inactive";
    mimeType = "audio/webm";
    constructor() { recorders.push(this); }
    start() { this.state = "recording"; }
    stop() {
      if (this.state !== "recording") return;
      this.state = "inactive";
      this.ondataavailable?.({ data: new Blob(["realistic test data"], { type: this.mimeType }) });
      this.onstop?.();
    }
  };
  Object.defineProperty(globalThis, "MediaRecorder", {
    value: Recorder, configurable: true, writable: true, enumerable: true
  });
  const microphone = load("../voice/microphoneDevices.ts", {}, { window: win });
  const { MicrophoneSettings } = load("../voice/MicrophoneSettings.tsx", {
    react: React, "../api": { transcribe: async () => ({ text: "ok", latency_ms: 12 }) },
    "./microphoneDevices": microphone,
  }, { window: win, navigator: { mediaDevices: media }, MediaRecorder: Recorder, Blob, Error });
  const { act } = require("react-dom/test-utils");
  const { createRoot } = require("react-dom/client");
  const container = doc.createElement("div");
  doc.body.appendChild(container);
  try {
    root = createRoot(container);
    let view;
    if (settingsView) {
      const settings = {
        model_name: "local", ollama_base_url: "http://127.0.0.1:11434", language: "de",
        whisper_binary: "auto", whisper_model_path: "", tts_engine: "piper",
        tts_voice: "", tts_model_path: "", say_rate_wpm: 235,
        tts_sir_pronunciation: "Sör", allowed_paths: []
      };
      const { IntelligentSettings } = load("../settings/IntelligentSettings.tsx", {
        react: React,
        "../api": {
          fetchModelInventory: async () => ({
            ollama: { status: "offline", models: [] },
            whisper: { models: [], binary_available: false, ffmpeg_available: false },
            tts: { piper_voices: [], say_supported: false }
          }),
          fetchInstallOptions: async () => ({ whisper_models: [], voices: [] }),
          fetchModelCatalog: async () => [],
          speak: async () => {}
        },
        "../setup/GuidedInstaller": { GuidedInstaller: () => null },
        "../setup/ModelCatalogBrowser": { ModelCatalogBrowser: () => null },
        "../voice/MicrophoneSettings": { MicrophoneSettings }
      }, { window: win, navigator: { mediaDevices: media }, AbortController });
      view = React.createElement(IntelligentSettings, {
        settings, draft: settings, setDraft() {},
        setupCheck: { state: "degraded", backendReachable: true,
          report: { stt: { status: "available" } } },
        sayVoices: [], onRefreshVoices: async () => {}, onSave: async () => {},
        onConfigured() {}, selectedMicId: "", onSelectMic() {},
        voiceActive: false, onStartVoiceTest() {}, onMicUnavailable() {},
        allowlistInput: "", onAllowlistInput() {}, onAddPath() {}, onRemovePath() {}
      });
    } else {
      view = React.createElement(MicrophoneSettings, {
        selectedId: "mic-usb", onSelect() {}, onDeviceUnavailable() {}, sttAvailable: false,
        voiceActive: false
      });
    }
    await act(async () => {
      root.render(React.createElement(React.StrictMode, null, view));
    });
    const buttons = () => container.descendants().filter(node => node.tagName === "BUTTON");
    const press = async label => {
      const button = buttons().find(node => node.textContent.includes(label));
      assert.ok(button, "button absent: " + label);
      const propsKey = Object.keys(button).find(key => key.startsWith("__reactProps$"));
      assert.ok(propsKey, "actual React DOM event props missing");
      await act(async () => { button[propsKey].onClick(); });
    };
    const button = label => buttons().find(node => node.textContent.includes(label));
    const buttonProps = label => {
      const node = button(label);
      assert.ok(node, "button absent: " + label);
      return node[Object.keys(node).find(key => key.startsWith("__reactProps$"))];
    };
    await callback({ press, button, buttonProps, setupCalls: () => setupCalls, cleanups: () => cleanups,
      nativePermission(status) { nativeStatus = status; },
      listenerCount: () => mediaListeners.get("devicechange")?.size || 0,
      async deviceChange(nextDevices) {
        devices = nextDevices;
        await act(async () => {
          for (const listener of [...mediaListeners.get("devicechange") || []]) listener();
        });
      },
      requests, intervals, tracks, contexts, recorders, text: () => container.textContent });
  } finally {
    if (root) await act(async () => { root.unmount(); });
    assert.equal(mediaListeners.get("devicechange")?.size || 0, 0, "unmount must remove every device listener");
    assert.equal(intervals.size, 0, "unmount must clear recorder timers");
  }
  } finally {
    for (const [key, descriptor] of Object.entries(originals)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  }
}

test("actual React.StrictMode setup-cleanup-setup still starts microphone, meter and finalization", async () => {
  await withMountedMicrophone(async ({ press, setupCalls, cleanups, requests, intervals, tracks, contexts, recorders, text }) => {
    assert.ok(setupCalls() >= 2, "actual React StrictMode must replay the device-listening effect");
    assert.ok(cleanups() >= 1, "actual React StrictMode cleanup must have occurred");
    await press("Mikrofon testen");
    assert.equal(requests.length, 1);
    assert.equal(requests[0].audio.deviceId.exact, "mic-usb");
    assert.equal(recorders.length, 1, "a recorder really started after strict effect replay");
    // React 18 batches state updates. The real analyzer interval must run in
    // act(), otherwise the text assertion observes the preceding render.
    await require("react-dom/test-utils").act(async () => {
      for (const callback of [...intervals.values()]) callback();
    });
    assert.match(text(), /Signal erkannt/);
    await press("Test beenden");
    assert.match(text(), /nicht-leerer MediaRecorder-Blob/);
    assert.equal(tracks[0].stops, 1);
    assert.equal(contexts[0].closed, 1);
    assert.equal(intervals.size, 0);
  });
});

test("real Settings and microphone lifecycle invalidates default-device proof outside the diagnostic", async () => {
  await withMountedMicrophone(async ({ press, buttonProps, listenerCount, deviceChange, nativePermission,
    requests, intervals, tracks, contexts, recorders, text }) => {
    assert.equal(listenerCount(), 1, "Settings owns the persistent device listener");
    await press("Mikrofon einrichten");
    assert.equal(listenerCount(), 2, "mounted diagnostic owns its separate capture listener");
    await press("Mikrofon testen");
    await require("react-dom/test-utils").act(async () => {
      for (const callback of [...intervals.values()]) callback();
    });
    await press("Test beenden");
    assert.match(text(), /nicht-leerer MediaRecorder-Blob bestätigt/);
    assert.equal(buttonProps("Jarvis hören lassen").disabled, false);

    await press("Übersicht");
    assert.equal(listenerCount(), 1, "diagnostic listener was removed on section change");
    assert.match(text(), /Hardwaretest erfolgreich/);
    await deviceChange([{ kind: "audioinput", deviceId: "mic-new", label: "New default Mic" }]);
    assert.match(text(), /Hardware noch nicht getestet/);
    assert.equal(requests.length, 1, "devicechange cannot open a microphone implicitly");
    await press("Mikrofon einrichten");
    assert.equal(listenerCount(), 2);
    assert.equal(buttonProps("Jarvis hören lassen").disabled, true);
    assert.doesNotMatch(text(), /echter RMS-Pegel erkannt/);

    await press("Mikrofon testen");
    await require("react-dom/test-utils").act(async () => {
      for (const callback of [...intervals.values()]) callback();
    });
    await press("Test beenden");
    assert.equal(buttonProps("Jarvis hören lassen").disabled, false);
    assert.equal(recorders.length, 2);
    assert.equal(requests.length, 2);
    nativePermission("denied");
    await press("Berechtigung erneut prüfen");
    assert.equal(buttonProps("Jarvis hören lassen").disabled, true);
    assert.doesNotMatch(text(), /echter RMS-Pegel erkannt|MediaStream tatsächlich geöffnet/);
    await press("Übersicht");
    assert.match(text(), /Hardware noch nicht getestet/);
    await press("Mikrofon einrichten");
    assert.equal(listenerCount(), 2, "repeated mounting cannot accumulate listeners");
    assert.ok(tracks.every(track => track.stops === 1));
    assert.ok(contexts.every(context => context.closed === 1));
  }, { settingsView: true });
});
