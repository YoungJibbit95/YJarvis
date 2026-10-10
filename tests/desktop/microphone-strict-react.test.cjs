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

async function withMountedMicrophone(callback) {
  const { doc, win, Node } = fakeDom();
  const original = {
    window: global.window, document: global.document, navigator: global.navigator,
    HTMLElement: global.HTMLElement, Node: global.Node,
    IS_REACT_ACT_ENVIRONMENT: global.IS_REACT_ACT_ENVIRONMENT
  };
  Object.assign(global, {
    window: win, document: doc, navigator: { userAgent: "node-react-strict-test" },
    HTMLElement: Node, Node, IS_REACT_ACT_ENVIRONMENT: true,
  });
  let root;
  const intervals = new Map(), requests = [], tracks = [], recorders = [], contexts = [];
  let intervalId = 0, setupCalls = 0, cleanups = 0;
  const track = { readyState: "live", enabled: true, stops: 0,
    stop() { this.stops++; this.readyState = "ended"; } };
  tracks.push(track);
  const stream = { getAudioTracks: () => [track], getTracks: () => [track] };
  const media = {
    async enumerateDevices() { return [{ kind: "audioinput", deviceId: "mic-usb", label: "USB Mic" }]; },
    async getUserMedia(options) { requests.push(options); return stream; },
    addEventListener() { setupCalls++; },
    removeEventListener() { cleanups++; },
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
  const previousRecorder = global.MediaRecorder;
  global.MediaRecorder = Recorder;
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
    await act(async () => {
      root.render(React.createElement(React.StrictMode, null, React.createElement(MicrophoneSettings, {
        selectedId: "mic-usb", onSelect() {}, onDeviceUnavailable() {}, sttAvailable: false,
        voiceActive: false
      })));
    });
    const buttons = () => container.descendants().filter(node => node.tagName === "BUTTON");
    const press = async label => {
      const button = buttons().find(node => node.textContent.includes(label));
      assert.ok(button, "button absent: " + label);
      const propsKey = Object.keys(button).find(key => key.startsWith("__reactProps$"));
      assert.ok(propsKey, "actual React DOM event props missing");
      await act(async () => { button[propsKey].onClick(); });
    };
    await callback({ press, setupCalls: () => setupCalls, cleanups: () => cleanups,
      requests, intervals, tracks, contexts, recorders, text: () => container.textContent });
  } finally {
    if (root) await act(async () => { root.unmount(); });
    global.MediaRecorder = previousRecorder;
    Object.assign(global, original);
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
    for (const callback of [...intervals.values()]) callback();
    assert.match(text(), /Signal erkannt/);
    await press("Test beenden");
    assert.match(text(), /nicht-leerer MediaRecorder-Blob/);
    assert.equal(tracks[0].stops, 1);
    assert.equal(contexts[0].closed, 1);
    assert.equal(intervals.size, 0);
  });
});
