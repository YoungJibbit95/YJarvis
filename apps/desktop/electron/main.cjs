const { app, BrowserWindow } = require("electron");
const path = require("path");
const { spawn } = require("child_process");

const AGENT_HOST = process.env.JARVIS_AGENT_HOST || "127.0.0.1";
const AGENT_PORT = process.env.JARVIS_AGENT_PORT || "8787";
const BACKEND_MANAGED_EXTERNALLY = process.env.JARVIS_BACKEND_MANAGED === "external";
const OPEN_DEVTOOLS = process.env.JARVIS_OPEN_DEVTOOLS === "1";
const ENABLE_AGENT_RELOAD = process.env.JARVIS_AGENT_RELOAD === "1";

let backendProcess = null;

function createWindow() {
  const window = new BrowserWindow({
    width: 1320,
    height: 860,
    backgroundColor: "#0f1116",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });

  if (!app.isPackaged) {
    window.loadURL("http://127.0.0.1:5173");
    if (OPEN_DEVTOOLS) {
      window.webContents.openDevTools({ mode: "detach" });
    }
  } else {
    window.loadFile(path.join(__dirname, "../dist/index.html"));
  }
}

function startBackend() {
  if (BACKEND_MANAGED_EXTERNALLY) {
    console.log("[jarvis] Backend wird extern verwaltet. Kein interner Spawn.");
    return;
  }

  const desktopDir = path.resolve(__dirname, "..");
  const projectRoot = path.resolve(desktopDir, "../..");
  const agentCwd = path.resolve(projectRoot, "apps/agent");
  const runtimeDir = path.resolve(projectRoot, "runtime");

  const pythonCandidates = [
    process.env.JARVIS_PYTHON_BIN,
    path.resolve(projectRoot, ".venv/bin/python"),
    "python3.11",
    "python3"
  ].filter(Boolean);

  const uvicornArgs = [
    "-m",
    "uvicorn",
    "jarvis_agent.main:app",
    "--host",
    AGENT_HOST,
    "--port",
    AGENT_PORT
  ];

  if (!app.isPackaged && ENABLE_AGENT_RELOAD) {
    uvicornArgs.push("--reload");
  }

  const env = {
    ...process.env,
    PYTHONPATH: `${agentCwd}${path.delimiter}${process.env.PYTHONPATH || ""}`,
    JARVIS_PROJECT_ROOT: projectRoot,
    JARVIS_RUNTIME_DIR: runtimeDir
  };

  const trySpawn = (index) => {
    if (index >= pythonCandidates.length) {
      console.error("[jarvis] Kein Python Interpreter gefunden (python3.11/python3).");
      return;
    }

    const pythonBin = pythonCandidates[index];
    console.log(`[jarvis] Starte Backend mit Python: ${pythonBin}`);
    const child = spawn(pythonBin, uvicornArgs, {
      cwd: agentCwd,
      env,
      stdio: ["ignore", "pipe", "pipe"]
    });

    child.once("error", (err) => {
      if (err.code === "ENOENT" || err.code === "EACCES") {
        trySpawn(index + 1);
        return;
      }
      console.error("[jarvis] Backend Startfehler:", err);
    });

    child.stdout.on("data", (chunk) => {
      process.stdout.write(`[agent] ${chunk}`);
    });

    child.stderr.on("data", (chunk) => {
      process.stderr.write(`[agent] ${chunk}`);
    });

    child.on("exit", (code, signal) => {
      backendProcess = null;
      if (!app.isQuitting) {
        console.error(`[jarvis] Backend beendet (code=${code}, signal=${signal}).`);
      }
    });

    backendProcess = child;
  };

  trySpawn(0);
}

function stopBackend() {
  if (!backendProcess) {
    return;
  }

  const pid = backendProcess.pid;
  backendProcess.kill("SIGTERM");
  backendProcess = null;
  if (pid) {
    console.log(`[jarvis] Backend Prozess ${pid} beendet.`);
  }
}

app.on("before-quit", () => {
  app.isQuitting = true;
  stopBackend();
});

app.whenReady().then(() => {
  startBackend();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
