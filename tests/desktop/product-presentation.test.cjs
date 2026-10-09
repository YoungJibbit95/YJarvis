const assert = require("node:assert/strict");
const { test } = require("node:test");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { load } = require("./load-setup.cjs");
const { PresenceStage, runStateLabel } = load("../app/PresenceStage.tsx");
const { ActionReview } = load("../app/ActionReview.tsx");
const { AppFeedback } = load("../app/AppFeedback.tsx");
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));

test("presence separates assistant work, microphone and dated agent events", () => {
  const idle = render(PresenceStage, { mode: "idle", microphoneActive: false });
  assert.ok(idle.includes("Im Ruhezustand") && idle.includes("Mikrofon aus"));
  assert.ok(!/Bereit|Verbunden|Letztes Agent-Ereignis/.test(idle));
  const thinking = render(PresenceStage, { mode: "thinking", microphoneActive: true,
    latestEvent: { id: "event", state: "approval_required", timestamp: "2026-10-08T12:00:00Z" } });
  for (const text of ["Anfrage aktiv", "Mikrofon aktiv", "Letztes Agent-Ereignis", "Freigabe benötigt"]) assert.ok(thinking.includes(text));
  const speaking = render(PresenceStage, { mode: "speaking", microphoneActive: false });
  assert.ok(speaking.includes("Sprachausgabe aktiv oder vorgemerkt"));
  assert.ok(!/Audiopegel|Lautstärke|hört zu/.test(speaking));
});

test("all real run states have distinct labels; unknown states stay neutral", () => {
  const states = ["received", "thinking", "approval_required", "executing", "done", "error"];
  assert.equal(new Set(states.map(runStateLabel)).size, states.length);
  assert.equal(runStateLabel("error"), "Vorgang fehlgeschlagen");
  for (const unknown of ["new_state", "constructor", "toString", "__proto__"]) assert.equal(runStateLabel(unknown), "Statusmeldung");
});

function approval(tool_name, tool_input) {
  return { id: "approval-42", run_id: "run-42", session_id: "session-42", tool_name, tool_input, status: "pending", requested_at: "2026-10-08T12:00:00Z" };
}

test("approval review retains every input and raw payload, including unusual data", () => {
  const html = render(ActionReview, { approval: approval("file_write", {
    path: "C:\\Preview\\plan.txt", content: "<script>alert(1)</script>\nSecond line",
    mode: "overwrite", extra: { enabled: false, count: 0, absent: null }
  }), onDecide() {} });
  for (const text of ["Datei schreiben", "Dateipfad", "Schreibmodus", "overwrite", "extra", "false", "0", "null", "run-42", "approval-42", "Vollständige Aktionsdaten"]) assert.ok(html.includes(text));
  assert.ok(html.includes("&lt;script&gt;") && !html.includes("<script>"));
  assert.ok(!/sicher|reversibel|ungefährlich|geringes Risiko/.test(html));
});

test("unknown approval tools get a neutral fallback and empty input remains explicit", () => {
  for (const name of ["new_tool", "constructor", "__proto__"]) {
    const html = render(ActionReview, { approval: approval(name, {}), onDecide() {} });
    assert.ok(html.includes("Aktion prüfen") && html.includes(name) && html.includes("Keine Eingabedaten übermittelt"));
  }
});

test("both approval controls dispatch the existing id and exact decision", () => {
  const calls = [];
  const tree = ActionReview({ approval: approval("open_url", { url: "https://example.org" }), onDecide: (...args) => calls.push(args) });
  function buttons(node) {
    if (!node || typeof node !== "object") return [];
    if (Array.isArray(node)) return node.flatMap(buttons);
    return node.type === "button" ? [node] : buttons(node.props?.children);
  }
  const controls = buttons(tree);
  assert.deepEqual(Array.from(controls, (button) => button.props.children), ["Freigeben", "Ablehnen"]);
  controls.forEach((button) => button.props.onClick());
  assert.deepEqual(calls, [["approval-42", "approve"], ["approval-42", "deny"]]);
});

test("connection and escaped failures are accessible outside diagnostics; dismissal keeps focus", () => {
  const props = { connection: { phase: "retry_wait", seconds: 4 }, failures: {
    chat: { title: "Nachricht konnte nicht gesendet werden", message: "<failure>" },
    voice: { title: "Sprachausgabe fehlgeschlagen", message: "TTS unavailable" }
  }, onDismiss() {} };
  const html = render(AppFeedback, props);
  assert.ok(html.includes('role="status"') && html.includes('aria-atomic="true"'));
  assert.ok(html.includes("Verbindung unterbrochen") && html.includes("4 s"));
  assert.equal((html.match(/role="alert"/g) || []).length, 2);
  assert.ok(!html.includes("<details") && html.includes("&lt;failure&gt;"));
  assert.ok(html.includes('aria-label="Fehlermeldungen" tabindex="0"'));
  const events = [];
  const tree = AppFeedback({ ...props, onDismiss: (kind) => events.push(kind) });
  const button = nodes(tree).find((node) => node.type === "button");
  button.props.onClick({ currentTarget: { closest: () => ({ focus: () => events.push("focus") }) } });
  assert.deepEqual(events, ["focus", "chat"]);
});

function nodes(node) {
  if (!node || typeof node !== "object") return [];
  if (Array.isArray(node)) return node.flatMap(nodes);
  return [node, ...nodes(node.props?.children)];
}

// Execute the real App callbacks with controlled API/transport/timers. This small
// hook driver renders only App; DOM/focus/layout are checked separately in Chromium.
async function appHarness(apiOverrides = {}) {
  const slots = [], effects = [], sockets = [], timers = new Map();
  let cursor = 0, dirty = true, tree, timerId = 0;
  const hooks = {
    ...React, memo: (component) => component,
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial;
      return [slots[index], (value) => {
        const next = typeof value === "function" ? value(slots[index]) : value;
        if (!Object.is(next, slots[index])) { slots[index] = next; dirty = true; }
      }];
    },
    useRef(value) { const index = cursor++; return slots[index] ??= { current: value }; },
    useMemo(factory) { return factory(); }, useCallback: (callback) => callback,
    useDeferredValue: (value) => value, useTransition: () => [false, (callback) => callback()],
    useEffect(callback, deps) {
      const index = cursor++, previous = slots[index];
      if (!previous || deps.some((dep, i) => !Object.is(dep, previous.deps[i]))) {
        slots[index] = { deps, cleanup: previous?.cleanup };
        effects.push(() => { slots[index].cleanup?.(); slots[index].cleanup = callback(); });
      }
    }
  };
  class Socket {
    static OPEN = 1; static CONNECTING = 0;
    readyState = 0;
    constructor(url) { this.url = url; sockets.push(this); }
    close() { this.readyState = 3; } // Tests deliver the browser close event explicitly.
    open() { this.readyState = 1; this.onopen(); }
    event(payload) { this.onmessage({ data: JSON.stringify(payload) }); }
  }
  const api = {
    createSession: async () => ({ session_id: "session-test" }),
    fetchMessages: async () => [], fetchApprovals: async () => [],
    fetchSettings: async () => ({ model_name: "model", language: "de", ollama_base_url: "http://fixture", tts_engine: "piper", tts_voice: "", say_rate_wpm: 235, tts_sir_pronunciation: "Sör", allowed_paths: [], whisper_binary: "auto", whisper_model_path: "", tts_model_path: "" }),
    fetchSmartHomeEntities: async () => [], fetchAudioVoices: async () => [],
    sendChat: async () => ({ run_id: "run-test" }), speak: async () => ({}),
    wsUrl: (id) => `ws://fixture/${id}`, ...apiOverrides
  };
  const AppShell = () => null, SetupNotice = () => null;
  const { default: App } = load("../App.tsx", {
    react: hooks, "./api": api, "./app/AppShell": { AppShell },
    "./app/AppFeedback": { AppFeedback }, "./app/PresenceStage": { PresenceStage, runStateLabel },
    "./app/ActionReview": { ActionReview }, "./voice/voiceReliability": load("../voice/voiceReliability.ts"),
    "./setup/SetupStatusView": { SetupNotice },
    "./setup/GuidedInstaller": { GuidedInstaller: () => null },
    "./settings/IntelligentSettings": { IntelligentSettings: () => null },
    "./voice/microphoneDevices": load("../voice/microphoneDevices.ts")
  }, {
    Error, WebSocket: Socket,
    navigator: { mediaDevices: { getUserMedia: async () => { throw new Error("Microphone denied"); } } },
    window: { addEventListener() {}, removeEventListener() {},
      setTimeout(callback, delay) { const id = ++timerId; timers.set(id, { callback, delay }); return id; },
      clearTimeout(id) { timers.delete(id); }, cancelAnimationFrame() {} }
  });
  async function settle() {
    for (let i = 0; i < 10; i++) {
      await Promise.resolve();
      if (dirty) {
        dirty = false; cursor = 0;
        tree = App({ setupCheck: { state: "degraded", backendReachable: true }, onRecheckSetup: async () => {} });
        effects.splice(0).forEach((effect) => effect());
      }
    }
  }
  await settle();
  const find = (predicate) => nodes(tree).find(predicate);
  return { sockets, api, settle, find,
    feedback: () => find((node) => node.type === AppFeedback).props,
    presence: () => find((node) => node.type === PresenceStage).props,
    diagnostic: () => find((node) => node.props?.className === "connection-details"),
    timer(delay) {
      const entry = [...timers].find(([, timer]) => timer.delay === delay);
      assert.ok(entry, `timer ${delay} exists`); timers.delete(entry[0]); entry[1].callback();
    },
    async send(text) {
      find((node) => node.type === "textarea").props.onChange({ target: { value: text } }); await settle();
      await find((node) => node.type === "form").props.onSubmit({ preventDefault() {} }); await settle();
    }
  };
}

test("Piper startup does not enumerate macOS say voices", async () => {
  let requests = 0;
  await appHarness({ fetchAudioVoices: async () => { requests++; return []; } });
  assert.equal(requests, 0);
});

test("real socket callbacks retain interruption through retries and recover only on open", async () => {
  const app = await appHarness();
  assert.equal(app.feedback().connection.phase, "connecting");
  app.sockets[0].open(); await app.settle();
  assert.equal(app.feedback().connection.phase, "connected");
  app.sockets[0].onerror(); await app.settle();
  assert.equal(app.feedback().connection.phase, "reconnecting");
  app.sockets[0].onclose(); await app.settle();
  assert.equal(app.feedback().connection.phase, "retry_wait");
  assert.equal(app.diagnostic().props.open, undefined);
  assert.ok(render(AppFeedback, app.feedback()).includes("Verbindung unterbrochen"));
  assert.equal(app.presence().mode, "idle"); // Idle never clears a transport warning.
  app.timer(350); await app.settle();
  assert.equal(app.feedback().connection.phase, "reconnecting");
  app.sockets[1].onclose(); await app.settle();
  app.timer(700); await app.settle();
  app.sockets[2].open(); await app.settle();
  assert.equal(app.feedback().connection.phase, "connected");
  assert.ok(!render(AppFeedback, app.feedback()).includes("Verbindung unterbrochen"));
  app.sockets[2].onclose(); await app.settle();
  app.timer(350); // Existing backoff reset remains intact.
});

test("failed chat and Voice callbacks remain visible across reconnect and navigation", async () => {
  const sent = [];
  const app = await appHarness({ sendChat: async (...args) => { sent.push(args); throw new Error("Chat rejected"); },
    speak: async () => { throw new Error("TTS unavailable"); } });
  app.sockets[0].open(); await app.settle();
  await app.send("  Test request  ");
  assert.deepEqual(sent, [["session-test", "Test request"]]);
  assert.equal(app.feedback().failures.chat.message, "Chat rejected");
  assert.equal(app.find((node) => node.props?.type === "submit").props.disabled, false);
  app.sockets[0].event({ event: "message", role: "assistant", content: "Eine fertige Antwort.", run_id: "run", timestamp: new Date().toISOString() });
  await app.settle();
  assert.equal(app.feedback().failures.voice.message, "TTS unavailable");
  app.sockets[0].onclose(); await app.settle(); app.timer(350); await app.settle();
  app.sockets[1].open(); await app.settle();
  assert.equal(app.feedback().connection.phase, "connected");
  assert.equal(Object.keys(app.feedback().failures).length, 2);
  app.find((node) => node.props?.onNavigate).props.onNavigate("settings"); await app.settle();
  assert.ok(render(AppFeedback, app.feedback()).includes("Chat rejected"));
  app.feedback().onDismiss("chat"); await app.settle();
  assert.equal(app.feedback().failures.chat, undefined);
  assert.equal(app.feedback().failures.voice.message, "TTS unavailable");
});

test("microphone startup rejection is visible and does not imply lost connection", async () => {
  const app = await appHarness();
  app.sockets[0].open(); await app.settle();
  app.find((node) => node.type === "button" && node.props.className?.trim() === "record").props.onClick();
  await app.settle();
  assert.equal(app.feedback().failures.voice.title, "Sprachmodus konnte nicht gestartet werden");
  assert.equal(app.feedback().failures.voice.message, "Microphone denied");
  assert.equal(app.feedback().connection.phase, "connected");
  assert.equal(app.presence().microphoneActive, false);
});
