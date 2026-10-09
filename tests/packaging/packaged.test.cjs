const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const os = require("node:os");
const { packagedBackendOptions, startPackagedBackend, rendererFile } = require("../../apps/desktop/electron/packaged.cjs");

test("installed backend uses bundled executable and writable data; preserves explicit data overrides", () => {
  const data = path.join(os.tmpdir(), "YJarvis data");
  const resources = path.join(os.tmpdir(), "Program Files", "resources");
  const options = packagedBackendOptions(resources, data, { JARVIS_AGENT_HOST: "remote", JARVIS_AGENT_PORT: "99", JARVIS_DB_PATH: "custom.db" });
  assert.equal(options.command, path.join(resources, "agent", process.platform === "win32" ? "jarvis-agent.exe" : "jarvis-agent"));
  assert.equal(packagedBackendOptions(resources, data, {}, "win32").command, path.join(resources, "agent", "jarvis-agent.exe"));
  assert.equal(packagedBackendOptions(resources, data, {}, "darwin").command, path.join(resources, "agent", "jarvis-agent"));
  assert.deepEqual(options.args, []);
  assert.equal(options.cwd, data);
  assert.equal(options.env.JARVIS_PROJECT_ROOT, data);
  assert.equal(options.env.JARVIS_RUNTIME_DIR, path.join(data, "runtime"));
  assert.equal(options.env.JARVIS_DB_PATH, "custom.db");
  assert.equal(options.env.JARVIS_AGENT_HOST, "127.0.0.1");
  assert.equal(options.env.JARVIS_AGENT_PORT, "8787");
  assert.equal(packagedBackendOptions(resources, data, { JARVIS_RUNTIME_DIR: "external-data" }).env.JARVIS_RUNTIME_DIR, "external-data");
});

test("externally managed backend is not spawned and data directories are not created", async () => {
  const owner = { start() { throw new Error("must not spawn"); } };
  assert.equal(await startPackagedBackend(owner, "missing", "missing", { JARVIS_BACKEND_MANAGED: "external" }), null);
});

test("bundled backend spawn failures propagate without Python fallback", async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "jarvis-packaging-"));
  const data = path.join(temp, "user data");
  let calls = 0;
  try {
    await assert.rejects(startPackagedBackend({ start: async () => { calls++; throw new Error("missing backend"); } }, temp, data, {}, async () => {}), /missing backend/);
    assert.equal(calls, 1);
    assert.ok(fs.statSync(data).isDirectory());
  } finally { fs.rmSync(temp, { recursive: true, force: true }); }
});

test("app protocol serves renderer assets and rejects other origins and escaped paths", () => {
  const root = path.join(os.tmpdir(), "dist");
  assert.equal(rendererFile("app://yjarvis/index.html", root), path.join(root, "index.html"));
  assert.equal(rendererFile("app://yjarvis/assets/main.js", root), path.join(root, "assets", "main.js"));
  for (const url of ["https://yjarvis/index.html", "app://other/index.html", "app://yjarvis:99/index.html", "app://user@yjarvis/index.html", "app://yjarvis/%2e%2e%2fsecret", "app://yjarvis/%2e%2e%5csecret"]) {
    // A backslash is an ordinary filename on POSIX; it escapes only on Windows.
    if (url.includes("%5c") && process.platform !== "win32") continue;
    assert.throws(() => rendererFile(url, root));
  }
});
