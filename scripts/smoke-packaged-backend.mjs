import path from "node:path";
import os from "node:os";
import fs from "node:fs";
import assert from "node:assert/strict";
import { OwnedProcesses, waitForHealth } from "./startup.cjs";
import { startPackagedBackend } from "../apps/desktop/electron/packaged.cjs";

const resources = path.resolve(process.argv[2] || "release/windows/win-unpacked/resources");
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "yjarvis-frozen-"));
let owner;
const base = "http://127.0.0.1:8787";
try {
  // Do not mistake a pre-existing local agent for the frozen backend under test.
  try {
    await fetch(`${base}/health`, { signal: AbortSignal.timeout(1000) });
    throw new Error("Port 8787 is already occupied; stop the local agent before this smoke test.");
  } catch (error) {
    if (!error.message.includes("fetch failed") && error.name !== "TimeoutError") throw error;
  }
  const env = { ...process.env, JARVIS_RUNTIME_DIR: path.join(temp, "runtime"), JARVIS_DB_PATH: path.join(temp, "runtime", "jarvis.db"), JARVIS_PROFILE_PATH: path.join(temp, "runtime", "jarvis_profile.json") };
  delete env.JARVIS_BACKEND_MANAGED;
  async function start() {
    owner = new OwnedProcesses();
    const child = await startPackagedBackend(owner, resources, temp, env);
    await waitForHealth(`${base}/health`, owner, child);
  }
  await start();
  const preflight = await fetch(`${base}/v1/sessions`, {
    method: "OPTIONS", headers: { Origin: "app://yjarvis", "Access-Control-Request-Method": "POST" }
  });
  assert.equal(preflight.status, 200);
  assert.equal(preflight.headers.get("access-control-allow-origin"), "app://yjarvis");
  const untrusted = await fetch(`${base}/health`, { headers: { Origin: "app://other" } });
  assert.equal(untrusted.headers.get("access-control-allow-origin"), null);
  const response = await fetch(`${base}/v1/sessions`, { method: "POST" });
  assert.equal(response.status, 200);
  const { session_id } = await response.json();
  assert.equal((await fetch(`${base}/v1/settings`)).status, 200);
  assert.equal((await fetch(`${base}/v1/setup/status`)).status, 200);
  const ws = new WebSocket(`ws://127.0.0.1:8787/v1/ws/${session_id}`);
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("WebSocket handshake timed out")), 5000);
    ws.addEventListener("open", () => { clearTimeout(timeout); ws.close(); resolve(); }, { once: true });
    ws.addEventListener("error", () => { clearTimeout(timeout); reject(new Error("WebSocket handshake failed")); }, { once: true });
  });
  await owner.stop();
  await start();
  const messages = await fetch(`${base}/v1/sessions/${session_id}/messages`);
  assert.equal(messages.status, 200);
  assert.deepEqual(await messages.json(), []);
  console.log("Frozen backend smoke passed: health, CORS, SQLite/session persistence, settings, setup, WebSocket, restart and owned cleanup.");
} finally {
  await owner?.stop();
  fs.rmSync(temp, { recursive: true, force: true });
}
