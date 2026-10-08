const path = require("node:path");
const fs = require("node:fs");
const net = require("node:net");

async function checkBackendPort(port = 8787) {
  await new Promise((resolve, reject) => {
    const server = net.createServer(socket => socket.destroy());
    server.once("error", (error) => reject(error.code === "EADDRINUSE"
      ? new Error(`Port ${port} wird bereits verwendet. Bitte die andere YJarvis-Instanz schließen oder einen extern verwalteten Backend-Start ausdrücklich konfigurieren.`)
      : error));
    server.listen(port, "127.0.0.1", () => server.close(resolve));
  });
}

function packagedBackendOptions(resourcesPath, userData, env = process.env) {
  return {
    command: path.join(resourcesPath, "agent", "jarvis-agent.exe"),
    args: [],
    cwd: userData,
    env: {
      ...env,
      JARVIS_PROJECT_ROOT: userData,
      JARVIS_RUNTIME_DIR: env.JARVIS_RUNTIME_DIR || path.join(userData, "runtime"),
      JARVIS_AGENT_HOST: "127.0.0.1",
      JARVIS_AGENT_PORT: "8787"
    }
  };
}

async function startPackagedBackend(owner, resourcesPath, userData, env = process.env, checkPort = checkBackendPort) {
  if (env.JARVIS_BACKEND_MANAGED === "external") return null;
  await checkPort();
  fs.mkdirSync(userData, { recursive: true });
  const { command, args, ...options } = packagedBackendOptions(resourcesPath, userData, env);
  return owner.start(command, args, options);
}

function rendererFile(url, root) {
  const parsed = new URL(url);
  if (parsed.protocol !== "app:" || parsed.hostname !== "yjarvis" || parsed.port || parsed.username || parsed.password) {
    throw new Error("Invalid application origin");
  }
  const file = path.resolve(root, `.${decodeURIComponent(parsed.pathname)}`);
  const relative = path.relative(root, file);
  if (relative.startsWith("..") || path.isAbsolute(relative)) throw new Error("Invalid application path");
  return file;
}

module.exports = { packagedBackendOptions, startPackagedBackend, rendererFile, checkBackendPort };
