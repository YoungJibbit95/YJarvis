import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { OwnedProcesses, startBackend, ollamaUrl, ensureOllama, waitForHealth } from "./startup.cjs";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const desktop = path.join(root, "apps", "desktop");
const mode = process.argv[2] || "all";
const owner = new OwnedProcesses();
let keepAlive;
let stopping;

function stop(code = 0) {
  stopping ??= owner.stop().catch((error) => {
    console.error("[startup] Cleanup failed:", error.message);
    code = 1;
  }).finally(() => {
    clearInterval(keepAlive);
    process.exitCode = code;
  });
  return stopping;
}

process.on("SIGINT", () => void stop());
process.on("SIGTERM", () => void stop());

function watch(child, name, normalExit = false) {
  if (!child) return;
  const exited = (code) => {
    if (!owner.stopped) {
      console.log(`[startup] ${name} exited (${code})`);
      void stop(normalExit && code === 0 ? 0 : 1);
    }
  };
  child.once("exit", exited);
  if (child.exitCode !== null || child.signalCode !== null) exited(child.exitCode);
}

try {
  if (!["all", "agent", "agent-reload", "ollama", "desktop"].includes(mode)) {
    throw new Error(`Unknown startup mode: ${mode}`);
  }
  if (mode === "all" || mode === "ollama") {
    const child = await ensureOllama(owner);
    watch(child, "Ollama");
    await waitForHealth(new URL("/api/tags", ollamaUrl()), owner, child);
    console.log(`[startup] Ollama ready (${child ? "owned" : "external; left running on exit"})`);
  }
  if (["all", "agent", "agent-reload", "desktop"].includes(mode)) {
    const child = await startBackend(owner, root, {
      reload: mode === "agent-reload" || (mode === "desktop" && process.env.JARVIS_AGENT_RELOAD === "1")
    });
    watch(child, "Agent");
    await waitForHealth(`http://${process.env.JARVIS_AGENT_HOST || "127.0.0.1"}:${process.env.JARVIS_AGENT_PORT || "8787"}/health`, owner, child);
    console.log(`[startup] Agent ready (${child ? "owned" : "external; left running on exit"})`);
  }
  if (mode === "all" || mode === "desktop") {
    const env = {
      ...process.env,
      VITE_JARVIS_AGENT_HOST: process.env.VITE_JARVIS_AGENT_HOST || process.env.JARVIS_AGENT_HOST || "127.0.0.1",
      VITE_JARVIS_AGENT_PORT: process.env.VITE_JARVIS_AGENT_PORT || process.env.JARVIS_AGENT_PORT || "8787",
      JARVIS_BACKEND_MANAGED: "external"
    };
    const viteBin = path.join(path.dirname(require.resolve("vite/package.json")), "bin", "vite.js");
    const vite = await owner.start(process.execPath, [viteBin], { cwd: desktop, env });
    watch(vite, "Vite");
    await waitForHealth("http://127.0.0.1:5173", owner, vite);
    const electron = await owner.start(require("electron"), ["."], { cwd: desktop, env, windowsHide: false });
    watch(electron, "Electron", true);
  }
  // Reused external services have no child handle to keep the standalone CLI alive.
  if (!owner.stopped) keepAlive = setInterval(() => {}, 60000);
} catch (error) {
  if (!owner.stopped) console.error("[startup]", error.message);
  await stop(owner.stopped ? 0 : 1);
}
