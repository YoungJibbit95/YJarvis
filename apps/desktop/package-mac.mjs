#!/usr/bin/env node
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { pythonCandidates } from "../../scripts/startup.cjs";

const require = createRequire(import.meta.url);
const desktopDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(desktopDir, "../..");

console.log(`🦊 YJarvis macOS Build Script (v${require("electron/package.json").version})`);
console.log(`   Platform: ${process.platform}, Architecture: ${process.arch}`);
if (process.platform !== "darwin") {
  throw new Error("This script must run on macOS.");
}

const buildDir = path.join(desktopDir, "dist");
const releaseDir = path.join(root, "release", process.arch === "arm64" ? "mac-arm64" : "mac-x64");

function run(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, stdio: "inherit", shell: false });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} failed (${result.status})`);
}

const python = pythonCandidates(root).find((candidate) => {
  const result = spawnSync(candidate, ["-c", "import sys; assert sys.version_info[:2] == (3, 11); import PyInstaller"], {
    cwd: root,
    stdio: "ignore",
    shell: false
  });
  return result.status === 0;
});
if (!python) throw new Error("Python 3.11 with PyInstaller is required. Install packaging/requirements.txt in the project virtual environment.");

run(python, ["-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", "build/agent", "--workpath", "build/pyinstaller", "packaging/agent.spec"], root);

if (!existsSync(path.join(buildDir, "index.html"))) {
  console.warn("⚠️  Building renderer assets...");
  const vitePath = path.join(path.dirname(require.resolve("vite/package.json")), "bin/vite.js");
  run(process.execPath, [vitePath, "build"], desktopDir);
}

console.log("\n📦 Package configuration from electron-builder.cjs...\n");

const buildArgs = [
  require.resolve("electron-builder/cli.js"),
  "--config",
  path.join(desktopDir, "electron-builder.cjs"),
  "--mac",
  process.arch === "arm64" ? "--arm64" : "--x64",
  "--publish",
  "never"
];

try {
  run(process.execPath, buildArgs, desktopDir);

  console.log("\n✅ macOS build completed successfully!");
  const releasePath = path.join(releaseDir, "YJarvis.app");
  console.log(`   Release bundle: ${releasePath}`);
} catch (e) {
  console.error(`❌ Build failed: ${e.message}`);
  throw e;
}
