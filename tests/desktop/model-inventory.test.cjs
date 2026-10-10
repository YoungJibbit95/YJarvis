const assert = require("node:assert/strict");
const { test } = require("node:test");
const React = require("react");
const { load } = require("./load-setup.cjs");

const { parseModelInventory } = load("modelInventory.ts");
const actualInventory = {
  ollama: {
    status: "online", active_model: "model-a:latest", error: null,
    models: [
      { name: "model-a:latest", digest: "sha-a", size_bytes: 800000, active: true, installed: true, verified_inference: false },
      { name: "model-b:latest", digest: "sha-b", size_bytes: 900000, active: false, installed: true, verified_inference: false },
    ]
  },
  whisper: {
    models: [
      { name: "small", path: "/runtime/models/ggml-small.bin", active: true, installed: true, verified_inference: false }
    ],
    binary_available: true, ffmpeg_available: true,
    active_path: "/runtime/models/ggml-small.bin", note: "File only"
  },
  tts: {
    piper_voices: [
      { name: "de_DE-voice-medium", path: "/runtime/models/piper/de_DE-voice-medium/de_DE-voice-medium.onnx",
        active: false, installed: true, paired_config: true, verified_playback: false }
    ],
    piper_runtime_available: true, say_supported: false, active_engine: "piper",
    active_path: "", note: "Only checked pair"
  }
};

function nodes(node) {
  if (Array.isArray(node)) return node.flatMap(nodes);
  if (!node || typeof node !== "object") return [];
  return [node, ...nodes(node.props?.children)];
}

function settings() {
  return {
    model_name: "model-a:latest", ollama_base_url: "http://127.0.0.1:11434",
    language: "de", tts_engine: "piper", tts_voice: "my-own-voice",
    tts_model_path: "/custom/voice.onnx", whisper_binary: "auto",
    whisper_model_path: "/runtime/models/ggml-small.bin", say_rate_wpm: 235,
    tts_sir_pronunciation: "Sör", allowed_paths: ["/own/workspace"]
  };
}

async function harness(inventoryResponse = actualInventory) {
  const slots = [], effects = [], reads = [], writes = [];
  let cursor = 0, dirty = true, tree;
  const props = {
    settings: settings(), draft: settings(),
    setDraft(update) {
      props.draft = typeof update === "function" ? update(props.draft) : update;
      dirty = true;
    },
    setupCheck: { state: "degraded", backendReachable: true },
    sayVoices: [], onRefreshVoices: async () => {}, onSave: async () => { writes.push(JSON.parse(JSON.stringify(props.draft))); },
    onConfigured: () => {}, selectedMicId: "", onSelectMic: () => {},
    voiceActive: false, onMicUnavailable: () => {}, allowlistInput: "",
    onAllowlistInput: () => {}, onAddPath: () => {}, onRemovePath: () => {},
  };
  const hooks = {
    ...React,
    useState(initial) {
      const id = cursor++;
      if (!(id in slots)) slots[id] = typeof initial === "function" ? initial() : initial;
      return [slots[id], value => {
        const next = typeof value === "function" ? value(slots[id]) : value;
        if (!Object.is(next, slots[id])) { slots[id] = next; dirty = true; }
      }];
    },
    useRef(v) { const id = cursor++; return slots[id] ??= { current: v }; },
    useMemo(fn) { return fn(); },
    useEffect(fn, deps) {
      const id = cursor++, before = slots[id];
      if (!before || deps.some((v, i) => !Object.is(v, before.deps[i]))) {
        slots[id] = { deps, cleanup: before?.cleanup };
        effects.push(() => { slots[id].cleanup?.(); slots[id].cleanup = fn(); });
      }
    }
  };
  const api = {
    async fetchModelInventory(signal) {
      reads.push(true);
      if (inventoryResponse instanceof Error) throw inventoryResponse;
      return parseModelInventory(inventoryResponse);
    },
    async speak() { throw new Error("Only saved TTS allowed"); }
  };
  const { IntelligentSettings } = load("../settings/IntelligentSettings.tsx", {
    react: hooks, "../api": api,
    "../setup/GuidedInstaller": { GuidedInstaller: function Installer() {} },
    "../setup/ModelCatalogBrowser": { ModelCatalogBrowser: function ModelCatalog() {} },
    "../voice/MicrophoneSettings": { MicrophoneSettings: function Mic() {} },
  }, { AbortController });

  async function settle() {
    for (let i = 0; i < 20; i++) {
      await Promise.resolve();
      if (dirty) {
        dirty = false;
        cursor = 0;
        tree = IntelligentSettings(props);
        effects.splice(0).forEach(fn => fn());
      }
    }
  }
  await settle();
  return {
    props, writes, reads, settle, nodes: () => nodes(tree),
    text: () => JSON.stringify(tree),
    click(label) {
      const b = nodes(tree).find(n => n.type === "button" && JSON.stringify(n.props.children).includes(label));
      assert.ok(b, "Missing button: " + label);
      b.props.onClick();
    },
  };
}

test("model inventory parser accepts verified source states but rejects fabricated records", () => {
  assert.equal(parseModelInventory(actualInventory).ollama.models[1].name, "model-b:latest");
  assert.throws(() => parseModelInventory({}), /Ungültiges/);
  assert.throws(() => parseModelInventory({
    ...actualInventory, ollama: { ...actualInventory.ollama, models: [{ name: 42 }] }
  }), /Ungültiger Ollama/);
  assert.throws(() => parseModelInventory({
    ...actualInventory, tts: { ...actualInventory.tts, piper_voices: [{ name: "bad" }] }
  }), /Ungültiger lokaler/);
});

test("installed Ollama choice changes draft only and retains advanced user fields", async () => {
  const h = await harness();
  h.click("KI & Modelle"); await h.settle();
  assert.match(h.text(), /model-a:latest/);
  assert.match(h.text(), /model-b:latest/);
  const select = h.nodes().find(n => n.type === "select" && n.props.value === "model-a:latest");
  assert.ok(select);
  select.props.onChange({ target: { value: "model-b:latest" } });
  await h.settle();
  assert.equal(h.props.draft.model_name, "model-b:latest");
  assert.equal(h.props.settings.model_name, "model-a:latest");
  assert.deepEqual(h.props.draft.allowed_paths, ["/own/workspace"]);
  assert.match(h.text(), /Nicht gespeicherte Änderungen/);
  h.click("Änderungen speichern"); await h.settle();
  assert.equal(h.writes.length, 1);
  assert.equal(h.writes[0].model_name, "model-b:latest");
  assert.deepEqual(h.writes[0].allowed_paths, ["/own/workspace"]);
});

test("unknown configured Ollama tag remains selectable without silent reset", async () => {
  const h = await harness({
    ...actualInventory, ollama: { ...actualInventory.ollama, models: [], status: "offline", error: "Offline" }
  });
  h.click("KI & Modelle"); await h.settle();
  assert.equal(h.props.draft.model_name, "model-a:latest");
  assert.match(h.text(), /Offline/);
  assert.match(h.text(), /nicht in aktueller Inventur bestätigt/);
});

test("Whisper and Piper selectors use only detected paths and complete voice pairs", async () => {
  const h = await harness();
  assert.match(h.text(), /Whisper CLI/);
  h.click("Sprachausgabe"); await h.settle();
  const voiceSelect = h.nodes().find(n => n.type === "select" && n.props.value === "/custom/voice.onnx");
  assert.ok(voiceSelect);
  voiceSelect.props.onChange({ target: {
    value: "/runtime/models/piper/de_DE-voice-medium/de_DE-voice-medium.onnx"
  } });
  await h.settle();
  assert.equal(h.props.draft.tts_voice, "de_DE-voice-medium");
  assert.equal(h.props.draft.tts_model_path, "/runtime/models/piper/de_DE-voice-medium/de_DE-voice-medium.onnx");
  assert.ok(!h.text().includes("macOS-Systemstimmen · say"));
  assert.match(h.text(), /Für diese Auswahl zuerst speichern/);
});

test("model inventory failure stays actionable with retry and does not mutate draft", async () => {
  const h = await harness(new Error("Backend unavailable"));
  h.click("KI & Modelle"); await h.settle();
  assert.match(h.text(), /Backend unavailable/);
  const before = JSON.stringify(h.props.draft);
  h.click("Erneut versuchen"); await h.settle();
  assert.ok(h.reads.length >= 2);
  assert.equal(JSON.stringify(h.props.draft), before);
});
