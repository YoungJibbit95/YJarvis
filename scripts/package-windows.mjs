import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import { pythonCandidates } from "./startup.cjs";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
if (process.platform !== "win32" || process.arch !== "x64") {
  throw new Error("Build the Windows x64 installer on native Windows x64.");
}
const python = pythonCandidates(root).find((candidate) => {
  const result = spawnSync(candidate, ["-c", "import sys; assert sys.version_info[:2] == (3, 11); import PyInstaller"], {
    cwd: root, stdio: "ignore", windowsHide: true, shell: false
  });
  return result.status === 0;
});
if (!python) throw new Error("Python 3.11 with packaging/requirements.txt and agent requirements is required.");

function run(command, args, cwd = root, env = process.env) {
  const result = spawnSync(command, args, { cwd, env, stdio: "inherit", windowsHide: true, shell: false });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} failed (${result.status})`);
}
run(python, ["-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", "build/agent", "--workpath", "build/pyinstaller", "packaging/agent.spec"]);
const desktop = path.join(root, "apps", "desktop");
// The installed renderer and backend use the same fixed loopback endpoint.
run(process.execPath, [path.join(path.dirname(require.resolve("vite/package.json")), "bin", "vite.js"), "build"], desktop, {
  ...process.env, VITE_JARVIS_AGENT_HOST: "127.0.0.1", VITE_JARVIS_AGENT_PORT: "8787"
});
run(process.execPath, [require.resolve("electron-builder/cli.js"), "--config", "electron-builder.cjs", "--win", "--x64", "--publish", "never"], desktop);
