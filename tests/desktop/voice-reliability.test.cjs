const assert = require("node:assert/strict");
const { test } = require("node:test");
const { load } = require("./load-setup.cjs");
const { WakeCommandWindow, OrderedSegmentProcessor, VoiceSubmissionQueue, recordingFileName } =
  load("../voice/voiceReliability.ts");

test("combined Jarvis utterance, two segments, no-wake block and consumed permission", () => {
  const window = new WakeCommandWindow(8000);
  assert.deepEqual({ ...window.accept("Jarvis, öffne Spotify", 1000) },
    { kind: "command", command: "öffne Spotify" });
  assert.equal(window.accept("Öffne Notizen", 1400).kind, "ignored");
  assert.equal(window.accept("Jarvis", 2100).kind, "wake");
  assert.deepEqual({ ...window.accept("Öffne Spotify", 2500) },
    { kind: "command", command: "Öffne Spotify" });
  assert.equal(window.accept("Öffne Spotify", 2600).kind, "ignored");
});

test("wakeword timeout uses captured time and repeated wakeword resets window", () => {
  const w = new WakeCommandWindow(6000);
  assert.equal(w.accept("Jarvis", 1000).kind, "wake");
  assert.equal(w.accept("Jarvis", 5200).kind, "wake");
  assert.equal(w.accept("Öffne Spotify", 10000).kind, "command");
  assert.equal(w.accept("Jarvis", 15000).kind, "wake");
  assert.equal(w.accept("Öffne Spotify", 21001).kind, "ignored");
  assert.equal(w.accept("Jarvis", 23000).kind, "wake");
  w.reset();
  assert.equal(w.accept("Öffne Spotify", 23001).kind, "ignored");
});

test("capture-ordered processing keeps commands after wake even if onstop events reorder", async () => {
  const pipeline = new OrderedSegmentProcessor();
  const gate = new WakeCommandWindow();
  const actions = [];
  pipeline.complete(2, async () => {
    const answer = gate.accept("Öffne Spotify", 2000);
    if (answer.kind === "command") actions.push(answer.command);
  });
  pipeline.complete(1, async () => {
    await Promise.resolve();
    assert.equal(gate.accept("Jarvis", 1000).kind, "wake");
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(actions, ["Öffne Spotify"]);
  pipeline.complete(3, async () => actions.push("3"));
  pipeline.complete(3, async () => actions.push("duplicate"));
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(actions, ["Öffne Spotify", "3"]);
});

test("error in one ordered STT task does not block a later recorder generation", async () => {
  const pipeline = new OrderedSegmentProcessor();
  const actions = [];
  pipeline.complete(1, async () => { throw new Error("whisper timed out"); });
  pipeline.complete(2, async () => { actions.push("after-failure"); });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(actions, ["after-failure"]);
  pipeline.cancel();
  pipeline.complete(3, async () => actions.push("unmounted"));
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(actions, ["after-failure"]);
});

test("single client submit, stable IDs, no retries after uncertain network outcome", () => {
  const q = new VoiceSubmissionQueue();
  q.add("1", "Jarvis, öffne Spotify", "öffne Spotify", 1000);
  q.add("1", "duplicate", "duplicate", 1000);
  q.add("2", "Jarvis, öffne Notizen", "öffne Notizen", 2000);
  assert.equal(q.snapshot().length, 2);
  const first = q.claimNext();
  assert.equal(first.id, "1");
  assert.equal(first.attempts, 1);
  assert.equal(q.claimNext(), null);
  q.settle("1", "pending", "ack may have been lost");
  assert.equal(q.claimNext(), null);
  assert.equal(q.snapshot()[0].state, "pending");
  assert.equal(q.retryByUser("1"), true);
  assert.equal(q.claimNext().attempts, 2);
  q.settle("1", "accepted", "run-1");
  assert.equal(q.claimNext().id, "2");
  q.settle("2", "failed", "HTTP 503");
  assert.equal(q.claimNext(), null);
  assert.equal(q.discardByUser("2"), true);
  assert.equal(q.snapshot().length, 1);
  assert.equal(q.snapshot()[0].runId, "run-1");
});

test("setup recheck pauses queue without losing or resending a pending command", () => {
  const q = new VoiceSubmissionQueue();
  q.add("first", "Jarvis, öffne Spotify", "öffne Spotify", 1000);
  let chatAvailable = false;
  if (chatAvailable) q.claimNext();
  assert.equal(q.snapshot()[0].state, "ready");
  chatAvailable = true;
  const sent = q.claimNext();
  assert.equal(sent.command, "öffne Spotify");
  q.settle(sent.id, "pending", "connection interrupted");
  chatAvailable = false;
  chatAvailable = true;
  if (chatAvailable) assert.equal(q.claimNext(), null);
  assert.equal(q.snapshot()[0].attempts, 1);
});

test("WebM, MP4, WAV and fallback filenames reflect recorder MIME", () => {
  for (const [type, file] of [
    ["audio/webm;codecs=opus", "recording.webm"],
    ["audio/mp4", "recording.mp4"],
    ["audio/mp4;codecs=mp4a.40.2", "recording.mp4"],
    ["audio/wav", "recording.wav"],
    ["audio/ogg", "recording.ogg"],
    ["", "recording.bin"]
  ]) assert.equal(recordingFileName(type), file);
});

test("actual transcribe API sends an MP4 container with MP4 filename and a bounded request", async () => {
  const { api, calls } = mockedApi(async () => ({
    ok: true, json: async () => ({ text: "Jarvis", language: "de", latency_ms: 5 })
  }));
  const blob = new Blob(["mp4-fixture"], { type: "audio/mp4" });
  const reply = await api.transcribe(blob);
  assert.equal(reply.text, "Jarvis");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.body.get("file").name, "recording.mp4");
  assert.equal(calls[0].options.signal.aborted, false);
});

test("actual chat API distinguishes definite HTTP rejection from uncertain transport errors", async () => {
  let failKind = "http";
  const { api } = mockedApi(async () => {
    if (failKind === "network") throw new Error("connection reset");
    if (failKind === "json") return { ok: true, json: async () => { throw new Error("truncated"); } };
    if (failKind === "success") return { ok: true, json: async () => ({ run_id: "run-5" }) };
    return { ok: false, status: 503, text: async () => '{"detail":"unavailable"}' };
  });
  await assert.rejects(() => api.sendChat("session", "hello"),
    (error) => error.outcome === "rejected");
  failKind = "network";
  await assert.rejects(() => api.sendChat("session", "hello"),
    (error) => error.outcome === "unknown");
  failKind = "json";
  await assert.rejects(() => api.sendChat("session", "hello"),
    (error) => error.outcome === "unknown");
  failKind = "success";
  assert.equal((await api.sendChat("session", "hello")).run_id, "run-5");
});

function mockedApi(handler) {
  const fs = require("node:fs");
  const path = require("node:path");
  const vm = require("node:vm");
  const ts = require("typescript");
  const file = path.resolve(__dirname, "../../apps/desktop/src/api.ts");
  const source = fs.readFileSync(file, "utf8").replace(/import\.meta\.env/g, "({})");
  const transpiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020
  } }).outputText;
  const calls = [], exports = {};
  vm.runInNewContext(transpiled, {
    exports, Blob, FormData, AbortSignal, URL, Error,
    require(name) { return name === "./voice/voiceReliability" ? { recordingFileName } : {}; },
    fetch: async (url, options) => {
      calls.push({ url, options });
      return handler(url, options);
    }
  }, { filename: file });
  return { api: exports, calls };
}
