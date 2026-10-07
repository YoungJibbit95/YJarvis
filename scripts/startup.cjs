// Shared by the development CLI and Electron; no shell commands or core imports.
const { spawn } = require("node:child_process");
const path = require("node:path");
const { setTimeout: delay } = require("node:timers/promises");

function pythonCandidates(root, env = process.env, platform = process.platform) {
  const paths = platform === "win32" ? path.win32 : path.posix;
  return [...new Set([
    env.JARVIS_PYTHON_BIN,
    paths.join(root, ".venv", platform === "win32" ? "Scripts" : "bin", platform === "win32" ? "python.exe" : "python"),
    ...(platform === "win32" ? ["python"] : ["python3.11", "python3"])
  ].filter(Boolean))];
}

function backendOptions(root, env = process.env, reload = false, platform = process.platform) {
  const paths = platform === "win32" ? path.win32 : path.posix;
  return {
    args: ["-m", "uvicorn", "jarvis_agent.main:app", "--host", env.JARVIS_AGENT_HOST || "127.0.0.1",
      "--port", env.JARVIS_AGENT_PORT || "8787", ...(reload ? ["--reload"] : [])],
    cwd: root,
    env: {
      ...env,
      PYTHONPATH: [paths.join(root, "apps", "agent"), env.PYTHONPATH].filter(Boolean).join(paths.delimiter),
      JARVIS_PROJECT_ROOT: env.JARVIS_PROJECT_ROOT || root,
      JARVIS_RUNTIME_DIR: env.JARVIS_RUNTIME_DIR || paths.join(root, "runtime")
    }
  };
}

class OwnedProcesses {
  constructor({ platform = process.platform, spawnProcess = spawn } = {}) {
    this.platform = platform;
    this.spawnProcess = spawnProcess;
    this.children = new Set();
    this.stopped = false;
    this.stopping = null;
  }

  async start(command, args, options = {}) {
    if (this.stopped) throw new Error("Startup cancelled");
    const child = this.spawnProcess(command, args, {
      stdio: "inherit", ...options,
      shell: false, windowsHide: options.windowsHide ?? true, detached: this.platform !== "win32"
    });
    const record = { child };
    record.closed = new Promise((resolve) => child.once("close", () => {
      this.children.delete(record);
      resolve();
    }));
    record.ready = new Promise((resolve, reject) => {
      child.once("spawn", resolve);
      child.once("error", reject);
    });
    this.children.add(record);
    await record.ready;
    if (this.stopped) throw new Error("Startup cancelled");
    return child;
  }

  stop() {
    this.stopped = true; // Also prevents a pending Python fallback from spawning.
    this.stopping ??= Promise.allSettled([...this.children].map(async (record) => {
      try { await record.ready; } catch { return; } // Failed spawn owns no process.
      const { child } = record;
      if (child.exitCode !== null || child.signalCode !== null) return;
      if (this.platform === "win32") {
        // Node's child.kill only terminates the parent on Windows. Include owned
        // uvicorn reload workers / Ollama runners, never a discovered server PID.
        await new Promise((resolve, reject) => {
          const killer = spawn("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], {
            shell: false, windowsHide: true, stdio: "ignore"
          });
          killer.once("error", reject);
          killer.once("exit", (code) => {
            if (code === 0 || child.exitCode !== null || child.signalCode !== null) resolve();
            else reject(new Error(`Could not stop owned process ${child.pid} (taskkill ${code})`));
          });
        });
      } else {
        const signalGroup = (signal) => {
          try { process.kill(-child.pid, signal); }
          catch (error) { if (error.code !== "ESRCH") throw error; }
        };
        signalGroup("SIGTERM");
        await Promise.race([record.closed, delay(2000)]);
        signalGroup("SIGKILL");
      }
      await record.closed;
    })).then((results) => {
      const failures = results.filter((result) => result.status === "rejected").map((result) => result.reason);
      if (failures.length) throw new AggregateError(failures, "Owned process cleanup failed");
    });
    return this.stopping;
  }
}

async function startBackend(owner, root, { env = process.env, reload = false } = {}) {
  if (env.JARVIS_BACKEND_MANAGED === "external") return null;
  const { args, ...options } = backendOptions(root, env, reload, owner.platform);
  const candidates = pythonCandidates(root, env, owner.platform);
  for (const command of candidates) {
    try { return await owner.start(command, args, options); }
    catch (error) {
      if (!["ENOENT", "EACCES"].includes(error.code)) throw error;
    }
  }
  throw new Error(`No Python interpreter found. Tried: ${candidates.join(", ")}. Set JARVIS_PYTHON_BIN to a Python 3.11 executable and install the project requirements.`);
}

function ollamaUrl(env = process.env) {
  const address = env.JARVIS_OLLAMA_HOST || env.JARVIS_OLLAMA_PORT
    ? `${env.JARVIS_OLLAMA_HOST || "127.0.0.1"}:${env.JARVIS_OLLAMA_PORT || "11434"}`
    : env.OLLAMA_HOST || "127.0.0.1:11434";
  return new URL(address.includes("://") ? address : `http://${address}`);
}

async function healthy(url) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(1000) });
    await response.body?.cancel();
    return response.ok;
  } catch { return false; }
}

async function ensureOllama(owner, env = process.env, probe = healthy) {
  const url = ollamaUrl(env);
  if (await probe(new URL("/api/tags", url))) return null;
  if (!["127.0.0.1", "localhost", "[::1]", "0.0.0.0"].includes(url.hostname)) {
    throw new Error(`External Ollama endpoint is unavailable: ${url.origin}`);
  }
  return owner.start("ollama", ["serve"], { env: { ...env, OLLAMA_HOST: url.origin } });
}

async function waitForHealth(url, owner, child, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (!owner.stopped && Date.now() < deadline) {
    if (child && (child.exitCode !== null || child.signalCode !== null)) {
      throw new Error(`Process exited before ${url} became ready (code=${child.exitCode}, signal=${child.signalCode})`);
    }
    if (await healthy(url)) return;
    await delay(200);
  }
  throw new Error(owner.stopped ? "Startup cancelled" : `Timed out waiting for ${url}`);
}

module.exports = { pythonCandidates, backendOptions, OwnedProcesses, startBackend, ollamaUrl, ensureOllama, healthy, waitForHealth };
