const test = require("node:test");
const assert = require("node:assert/strict");
const { once, EventEmitter } = require("node:events");
const { spawn, execFileSync } = require("node:child_process");
const { mkdtemp, rm } = require("node:fs/promises");
const { existsSync, readFileSync } = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const http = require("node:http");
const vm = require("node:vm");
const { setTimeout: delay } = require("node:timers/promises");
const { pythonCandidates, backendOptions, OwnedProcesses, startBackend, ollamaUrl,
  ensureOllama, healthy, waitForHealth } = require("../../scripts/startup.cjs");

const root = path.resolve(__dirname, "../..");
const venv = pythonCandidates(root, {})[0];
const python = process.env.JARVIS_TEST_PYTHON || (existsSync(venv) ? venv : "python");
const quietOwner = () => new OwnedProcesses({
  spawnProcess: (command, args, options) => spawn(command, args, { ...options, stdio: "ignore" })
});

test("Windows discovery: explicit executable, project venv, PATH python", () => {
  assert.deepEqual(pythonCandidates("C:\\Work Space", { JARVIS_PYTHON_BIN: "D:\\Python 3\\python.exe" }, "win32"),
    ["D:\\Python 3\\python.exe", "C:\\Work Space\\.venv\\Scripts\\python.exe", "python"]);
  assert.deepEqual(pythonCandidates("C:\\Work", {}, "win32"), ["C:\\Work\\.venv\\Scripts\\python.exe", "python"]);
});

for (const platform of ["darwin", "linux"]) {
  test(`${platform} keeps explicit Python, .venv/bin/python, python3.11 and python3`, () => {
    assert.deepEqual(pythonCandidates("/work space", { JARVIS_PYTHON_BIN: "/custom/python" }, platform),
      ["/custom/python", "/work space/.venv/bin/python", "python3.11", "python3"]);
  });
}

for (const [platform, base, oldPath, expected] of [
  ["win32", "C:\\Work Space", "C:\\extra;D:\\modules", "C:\\Work Space\\apps\\agent;C:\\extra;D:\\modules"],
  ["darwin", "/work space", "/extra:/modules", "/work space/apps/agent:/extra:/modules"]
]) {
  test(`${platform} backend argv and environment preserve configuration without shell syntax`, () => {
    const env = { PYTHONPATH: oldPath, JARVIS_AGENT_HOST: "localhost", JARVIS_AGENT_PORT: "9876",
      JARVIS_RUNTIME_DIR: "custom runtime", JARVIS_DB_PATH: "custom.db", JARVIS_AGENT_RELOAD: "1" };
    const options = backendOptions(base, env, true, platform);
    assert.deepEqual(options.args, ["-m", "uvicorn", "jarvis_agent.main:app", "--host", "localhost", "--port", "9876", "--reload"]);
    assert.equal(options.cwd, base);
    assert.equal(options.env.PYTHONPATH, expected);
    assert.equal(options.env.JARVIS_RUNTIME_DIR, "custom runtime");
    assert.equal(options.env.JARVIS_DB_PATH, "custom.db");
    assert.equal(options.env.JARVIS_PROJECT_ROOT, base);
    assert.equal(env.PYTHONPATH, oldPath);
    assert.ok(!backendOptions(base, {}, false, platform).args.includes("--reload"));
  });
}

test("Python spawn ENOENT/EACCES falls back in order, retaining executable/argv separation", async () => {
  const calls = [];
  const backend = {};
  const owner = { platform: "win32", start: async (...args) => {
    calls.push(args);
    if (calls.length < 3) throw Object.assign(new Error("unavailable"), { code: calls.length === 1 ? "ENOENT" : "EACCES" });
    return backend;
  } };
  assert.equal(await startBackend(owner, "C:\\project", { env: { JARVIS_PYTHON_BIN: "C:\\Python Space\\python.exe" } }), backend);
  assert.deepEqual(calls.map(([command]) => command), ["C:\\Python Space\\python.exe", "C:\\project\\.venv\\Scripts\\python.exe", "python"]);
  assert.equal(calls[0][1][0], "-m");
});

test("missing Python reports all candidates; other spawn errors do not fall through", async () => {
  const owner = { platform: "darwin", start: async () => { throw Object.assign(new Error("missing"), { code: "ENOENT" }); } };
  await assert.rejects(startBackend(owner, "/project", { env: {} }), /No Python interpreter found.*python3\.11.*JARVIS_PYTHON_BIN/);
  owner.start = async () => { throw Object.assign(new Error("resource failure"), { code: "EMFILE" }); };
  await assert.rejects(startBackend(owner, "/project", { env: {} }), /resource failure/);
});

test("Ollama reuses a responding external HTTP endpoint and never owns it", async (t) => {
  const server = http.createServer((req, res) => { assert.equal(req.url, "/api/tags"); res.end('{"models":[]}'); });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const env = { JARVIS_OLLAMA_PORT: String(server.address().port) };
  const owner = new OwnedProcesses({ spawnProcess: () => { assert.fail("external Ollama must not spawn"); } });
  assert.equal(await ensureOllama(owner, env), null);
  await owner.stop();
  assert.equal(await healthy(new URL("/api/tags", ollamaUrl(env))), true);
});

test("unavailable local Ollama is spawned once, with explicit host environment", async () => {
  const calls = [];
  const child = {};
  const owner = { start: async (...args) => { calls.push(args); return child; } };
  assert.equal(await ensureOllama(owner, { JARVIS_OLLAMA_PORT: "11499", OLLAMA_MODELS: "models with spaces" }, async () => false), child);
  assert.deepEqual(calls, [["ollama", ["serve"], { env: {
    JARVIS_OLLAMA_PORT: "11499", OLLAMA_MODELS: "models with spaces", OLLAMA_HOST: "http://127.0.0.1:11499"
  } }]]);
  assert.equal(ollamaUrl({ OLLAMA_HOST: "localhost:11500" }).origin, "http://localhost:11500");
  await assert.rejects(ensureOllama(owner, { OLLAMA_HOST: "http://192.0.2.1:11434" }, async () => false), /External Ollama endpoint is unavailable/);
  assert.equal(calls.length, 1);
});

test("real spawn failure is caught, and owner cannot launch after shutdown", async () => {
  const owner = quietOwner();
  await assert.rejects(owner.start(path.join(os.tmpdir(), "yjw-missing-executable"), []), { code: "ENOENT" });
  await owner.stop();
  await assert.rejects(owner.start(process.execPath, ["-e", "process.exit(0)"]), /Startup cancelled/);
});

test("shutdown during pending spawn waits and terminates the owned child", async () => {
  const owner = quietOwner();
  const starting = owner.start(process.execPath, ["-e", "setInterval(() => {}, 1000)"]);
  const stopping = owner.stop();
  await assert.rejects(starting, /Startup cancelled/);
  await stopping;
  assert.equal(owner.children.size, 0);
});

test("shell metacharacters and spaces remain literal argv/environment data", async (t) => {
  const owner = new OwnedProcesses();
  t.after(() => owner.stop());
  const literal = 'path with spaces; $(echo unsafe) & "quoted"';
  const child = await owner.start(process.execPath, ["-e", "process.send([process.argv[1], process.env.TEST_LITERAL]); setInterval(() => {}, 1000)", literal], {
    env: { ...process.env, TEST_LITERAL: literal }, stdio: ["ignore", "ignore", "ignore", "ipc"]
  });
  const [message] = await once(child, "message");
  assert.deepEqual(message, [literal, literal]);
});

test("early process exit and readiness timeout are reported", async (t) => {
  const owner = quietOwner();
  t.after(() => owner.stop());
  const child = await owner.start(process.execPath, ["-e", "process.exit(7)"]);
  await once(child, "exit");
  await assert.rejects(waitForHealth("http://127.0.0.1:1/health", owner, child), /Process exited.*code=7/);
  await assert.rejects(waitForHealth("http://127.0.0.1:1/health", owner, null, 20), /Timed out/);
});

test("Electron retains macOS activation and waits through repeated quit events", async () => {
  const app = new EventEmitter();
  app.whenReady = async () => {};
  app.quit = () => { app.quitCalls = (app.quitCalls || 0) + 1; };
  let windows = [];
  class BrowserWindow {
    constructor() { windows.push(this); }
    loadURL(url) { this.url = url; }
    static getAllWindows() { return windows; }
  }
  let finishCleanup;
  const owner = { stopped: false, stop: () => {
    owner.stopped = true;
    return new Promise((resolve) => { finishCleanup = resolve; });
  } };
  const processStub = new EventEmitter();
  processStub.platform = "darwin";
  processStub.env = { JARVIS_AGENT_RELOAD: "1" };
  vm.runInNewContext(readFileSync(path.join(root, "apps/desktop/electron/main.cjs"), "utf8"), {
    __dirname: path.join(root, "apps/desktop/electron"), process: processStub, console,
    require: (name) => {
      if (name === "electron") return { app, BrowserWindow };
      if (name === "path") return path;
      assert.equal(name, "../../../scripts/startup.cjs");
      return { OwnedProcesses: function () { return owner; }, startBackend: async (actualOwner, actualRoot, options) => {
        assert.equal(actualOwner, owner);
        assert.equal(actualRoot, root);
        assert.equal(options.reload, true);
        return new EventEmitter();
      } };
    }
  });
  await new Promise(setImmediate);
  assert.equal(windows.length, 1);
  assert.equal(windows[0].url, "http://127.0.0.1:5173");
  windows = [];
  app.emit("window-all-closed");
  assert.equal(app.quitCalls, undefined, "macOS remains active after closing its last window");
  app.emit("activate");
  assert.equal(windows.length, 1);
  let prevented = 0;
  const quitEvent = { preventDefault: () => { prevented++; } };
  app.emit("before-quit", quitEvent);
  app.emit("before-quit", quitEvent);
  assert.equal(prevented, 2, "a second quit must not bypass pending cleanup");
  assert.equal(app.quitCalls, undefined);
  finishCleanup();
  await new Promise(setImmediate);
  assert.equal(app.quitCalls, 1);
  app.emit("before-quit", quitEvent);
  assert.equal(prevented, 2, "quit is allowed only once cleanup completed");
});

// Actual Python, Uvicorn and SQLite; no models, GUI, audio devices or native tools.
for (const reload of [false, true]) {
  test(`native backend health, SQLite, session and owned shutdown (reload=${reload})`, { timeout: 45000 }, async (t) => {
    const runtime = await mkdtemp(path.join(os.tmpdir(), "yjw startup space ; "));
    const owner = quietOwner();
    t.after(async () => { await owner.stop(); await rm(runtime, { recursive: true, force: true }); });
    const portServer = http.createServer();
    portServer.listen(0, "127.0.0.1");
    await once(portServer, "listening");
    const port = portServer.address().port;
    await new Promise((resolve) => portServer.close(resolve));
    const env = { ...process.env, JARVIS_PYTHON_BIN: python, JARVIS_AGENT_HOST: "127.0.0.1",
      JARVIS_AGENT_PORT: String(port), JARVIS_RUNTIME_DIR: runtime,
      JARVIS_DB_PATH: path.join(runtime, "smoke.db"), JARVIS_PROFILE_PATH: path.join(runtime, "profile.json") };
    delete env.JARVIS_BACKEND_MANAGED;
    const child = await startBackend(owner, root, { env, reload });
    const base = `http://127.0.0.1:${port}`;
    await waitForHealth(`${base}/health`, owner, child);
    assert.deepEqual(await (await fetch(`${base}/health`)).json(), { status: "ok" });
    const sessionResponse = await fetch(`${base}/v1/sessions`, { method: "POST" });
    assert.equal(sessionResponse.status, 200);
    const session = await sessionResponse.json();
    assert.ok(session.session_id);
    const databaseCounts = execFileSync(python, ["-c", "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('select count(*) from sessions where id=?', (sys.argv[2],)).fetchone()[0]); print(c.execute('select count(*) from schema_migrations where version=1').fetchone()[0])", env.JARVIS_DB_PATH, session.session_id], { encoding: "utf8" });
    assert.deepEqual(databaseCounts.trim().split(/\r?\n/), ["1", "1"]);

    const externalOwner = quietOwner();
    assert.equal(await startBackend(externalOwner, root, { env: { ...env, JARVIS_BACKEND_MANAGED: "external" } }), null);
    await externalOwner.stop();
    assert.equal(await healthy(`${base}/health`), true, "external owner must leave the real backend running");
    await owner.stop();
    for (let retry = 0; retry < 20 && await healthy(`${base}/health`); retry++) await delay(100);
    assert.equal(await healthy(`${base}/health`), false, "owned backend including reload worker must stop");
    assert.equal(owner.children.size, 0);
  });
}
