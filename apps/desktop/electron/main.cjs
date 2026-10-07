const { app, BrowserWindow } = require("electron");
const path = require("path");
const { OwnedProcesses, startBackend } = require("../../../scripts/startup.cjs");

const OPEN_DEVTOOLS = process.env.JARVIS_OPEN_DEVTOOLS === "1";
const ENABLE_AGENT_RELOAD = process.env.JARVIS_AGENT_RELOAD === "1";

const backendOwner = new OwnedProcesses();
let backendStopped = false;

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

// Wait for owned process cleanup before Electron exits. An externally managed
// backend never enters this owner, so quitting the UI cannot terminate it.
app.on("before-quit", (event) => {
  app.isQuitting = true;
  if (!backendStopped) {
    event.preventDefault();
    if (!backendOwner.stopped) {
      backendOwner.stop().catch((error) => console.error("[jarvis] Backend cleanup:", error))
        .finally(() => { backendStopped = true; app.quit(); });
    }
  }
});

process.on("SIGINT", () => app.quit());
process.on("SIGTERM", () => app.quit());

app.whenReady().then(async () => {
  const projectRoot = path.resolve(__dirname, "../../..");
  try {
    const child = await startBackend(backendOwner, projectRoot, {
      reload: !app.isPackaged && ENABLE_AGENT_RELOAD
    });
    child?.on("exit", (code, signal) => {
      if (!app.isQuitting) console.error(`[jarvis] Backend exited (code=${code}, signal=${signal}).`);
    });
  } catch (error) {
    if (!app.isQuitting) console.error("[jarvis] Backend startup:", error.message);
  }
  if (app.isQuitting) return;
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
