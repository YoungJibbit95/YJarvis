const { app, BrowserWindow, protocol, net, dialog, Menu, ipcMain, session, systemPreferences } = require("electron");
const path = require("path");
const { pathToFileURL } = require("node:url");
const { OwnedProcesses, startBackend, waitForHealth, ensureOllama, ollamaUrl } = require(app.isPackaged
  ? path.join(process.resourcesPath, "startup.cjs")
  : "../../../scripts/startup.cjs");
const { startPackagedBackend, rendererFile } = require("./packaged.cjs");
const { installMicrophonePermissions, isTrustedRenderer, nativeMicStatus } = require("./microphone-permissions.cjs");

protocol.registerSchemesAsPrivileged([{
  scheme: "app", privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true }
}]);

// macOS has a system app menu (including Quit), rather than an in-window menu.
if (process.platform !== "darwin") Menu.setApplicationMenu(null);
ipcMain.on("jarvis:window-control", (event, action) => {
  const frame = event.senderFrame;
  if (!frame || frame !== event.sender.mainFrame) return;
  const url = new URL(frame.url);
  if (app.isPackaged ? url.protocol !== "app:" || url.host !== "yjarvis" || url.username || url.password
    : url.origin !== "http://127.0.0.1:5173") return;
  const window = BrowserWindow.fromWebContents(event.sender);
  if (!window) return;
  if (action === "close") window.close();
  else if (action === "minimize") window.minimize();
  else if (action === "toggle-maximize") {
    if (window.isMaximized()) window.unmaximize();
    else window.maximize();
  }
});

const OPEN_DEVTOOLS = process.env.JARVIS_OPEN_DEVTOOLS === "1";
const ENABLE_AGENT_RELOAD = process.env.JARVIS_AGENT_RELOAD === "1";

ipcMain.handle("jarvis:microphone-permission-status", (event) => {
  const frame = event.senderFrame;
  if (!frame || frame !== event.sender.mainFrame ||
      !isTrustedRenderer(event.sender, frame.url, app.isPackaged, () => BrowserWindow.getAllWindows())) {
    return "unknown";
  }
  // Windows' status alone never proves the audio device can be opened.
  return nativeMicStatus(process.platform, systemPreferences);
});

const backendOwner = new OwnedProcesses();
let backendStopped = false;

function createWindow() {
  const window = new BrowserWindow({
    width: 1320,
    height: 860,
    frame: false,
    autoHideMenuBar: true,
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
    window.loadURL("app://yjarvis/index.html");
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
  installMicrophonePermissions(session.defaultSession, {
    packaged: app.isPackaged, platform: process.platform, systemPreferences,
    getWindows: () => BrowserWindow.getAllWindows()
  });
  const projectRoot = path.resolve(__dirname, "../../..");
  try {
    if (app.isPackaged) {
      protocol.handle("app", (request) => {
        try {
          return net.fetch(pathToFileURL(rendererFile(request.url, path.join(__dirname, "../dist"))).href);
        } catch {
          return new Response("Not found", { status: 404 });
        }
      });
    }
    const child = app.isPackaged
      ? await startPackagedBackend(backendOwner, process.resourcesPath, app.getPath("userData"))
      : await startBackend(backendOwner, projectRoot, { reload: ENABLE_AGENT_RELOAD });
    child?.on("exit", (code, signal) => {
      if (!app.isQuitting) console.error(`[jarvis] Backend exited (code=${code}, signal=${signal}).`);
    });
    if (app.isPackaged) {
      // Ollama is optional during setup. Reuse an existing server, or own only
      // the server started here. Missing installations leave setup accessible.
      try {
        const ollama = await ensureOllama(backendOwner);
        await waitForHealth(new URL("/api/tags", ollamaUrl()), backendOwner, ollama);
      } catch (error) {
        if (!app.isQuitting) console.error("[jarvis] Ollama startup:", error.message);
      }
    }
    if (app.isPackaged) await waitForHealth("http://127.0.0.1:8787/health", backendOwner, child);
  } catch (error) {
    if (!app.isQuitting) console.error("[jarvis] Backend startup:", error.message);
    if (app.isPackaged && !app.isQuitting) {
      dialog.showErrorBox("YJarvis konnte nicht starten", error.message);
      app.quit();
      return;
    }
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
