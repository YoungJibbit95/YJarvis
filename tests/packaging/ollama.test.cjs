const test = require("node:test");
const assert = require("node:assert/strict");
const { ensureOllama } = require("../../scripts/startup.cjs");

test("Windows Ollama discovery falls back to the standard installer location without a shell", async () => {
  const calls = [];
  const owner = { platform: "win32", stopped: false, async start(command, args, options) {
    calls.push({ command, args, options });
    if (command === "ollama") throw Object.assign(new Error("not on PATH"), { code: "ENOENT" });
    return "owned-server";
  } };
  assert.equal(await ensureOllama(owner, { LOCALAPPDATA: "C:\\User Data" }, async () => false), "owned-server");
  assert.deepEqual(calls.map(x => x.command), ["ollama", "C:\\User Data\\Programs\\Ollama\\ollama.exe"]);
  assert.deepEqual(calls[1].args, ["serve"]);
  assert.equal(calls[1].options.env.OLLAMA_HOST, "http://127.0.0.1:11434");
});

test("Windows launch reuses an existing Ollama server without taking ownership", async () => {
  assert.equal(await ensureOllama({ stopped: false, start() { throw new Error("must not spawn"); } }, {}, async () => true), null);
});

test("missing Ollama and cancelled fallback fail explicitly", async () => {
  await assert.rejects(ensureOllama({ platform: "win32", stopped: false, async start() { throw Object.assign(new Error("missing"), { code: "ENOENT" }); } }, {}, async () => false), /Ollama executable not found/);
  const owner = { platform: "win32", stopped: false, async start() { owner.stopped = true; throw new Error("Startup cancelled"); } };
  await assert.rejects(ensureOllama(owner, { LOCALAPPDATA: "C:\\User" }, async () => false), /Startup cancelled/);
});
