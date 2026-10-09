const test = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

for (const scenario of ["healthy", "backend-missing", "ollama-missing"]) {
  test(`installed main uses resource backend, waits for health and handles failure (${scenario})`, async () => {
    const app = new EventEmitter();
    Object.assign(app, { isPackaged: true, whenReady: async () => {}, getPath: () => "user-data", quit: () => { app.quitCalled = true; } });
    const processStub = new EventEmitter();
    Object.assign(processStub, { env: {}, platform: "win32", resourcesPath: "resources" });
    const calls = [];
    let handler;
    let windowControl;
    let permissionRequest, permissionCheck, permissionStatus;
    const windows = [];
    const mediaSession = {
      setPermissionRequestHandler(fn) { permissionRequest = fn; },
      setPermissionCheckHandler(fn) { permissionCheck = fn; }
    };
    const owner = {};
    class BrowserWindow {
      constructor(options) {
        assert.equal(options.frame, false); assert.equal(options.autoHideMenuBar, true);
        this.webContents = { mainFrame: { url: "" } };
        windows.push(this);
        calls.push("window");
      }
      loadURL(url) { this.webContents.mainFrame.url = url; calls.push(url); }
      static getAllWindows() { return windows; }
      static fromWebContents() { return { close() { calls.push("close"); }, minimize() { calls.push("minimize"); }, isMaximized() { return false; }, maximize() { calls.push("maximize"); } }; }
    }
    const startup = {
      OwnedProcesses: function () { return owner; },
      startBackend: () => { throw new Error("legacy backend must not be used"); },
      waitForHealth: async (url, actualOwner) => {
        assert.ok(String(url) === "http://127.0.0.1:8787/health" || String(url) === "http://127.0.0.1:11434/api/tags");
        assert.equal(actualOwner, owner);
        calls.push("health");
      }
    };
    startup.ensureOllama = async () => {
      if (scenario === "ollama-missing") throw new Error("Ollama not installed");
      return null;
    };
    startup.ollamaUrl = () => new URL("http://127.0.0.1:11434");
    const packaged = {
      rendererFile: require("../../apps/desktop/electron/packaged.cjs").rendererFile,
      startPackagedBackend: async (actualOwner, resources, data) => {
        assert.equal(actualOwner, owner);
        assert.equal(resources, "resources");
        assert.equal(data, "user-data");
        calls.push("backend");
        if (scenario === "backend-missing") throw new Error("backend missing");
        return new EventEmitter();
      }
    };
    const source = fs.readFileSync(path.join(__dirname, "../../apps/desktop/electron/main.cjs"), "utf8");
    vm.runInNewContext(source, {
      __dirname: "electron", process: processStub, console: { error() {} }, Response, URL,
      require(name) {
        if (name === "electron") return {
          app, BrowserWindow,
          session: { defaultSession: mediaSession },
          systemPreferences: { getMediaAccessStatus: () => "unknown", askForMediaAccess: async () => false },
          Menu: { setApplicationMenu(menu) { assert.equal(menu, null); } },
          ipcMain: {
            on(channel, callback) { assert.equal(channel, "jarvis:window-control"); windowControl = callback; },
            handle(channel, callback) { assert.equal(channel, "jarvis:microphone-permission-status"); permissionStatus = callback; }
          },
          protocol: { registerSchemesAsPrivileged(schemes) { assert.equal(schemes[0].privileges.corsEnabled, true); }, handle(scheme, callback) { assert.equal(scheme, "app"); handler = callback; } },
          dialog: { showErrorBox(title, message) { assert.equal(message, "backend missing"); calls.push("error"); } }
        };
        if (name === "path" || name === "node:url") return require(name);
        if (name === path.join("resources", "startup.cjs")) return startup;
        if (name === "./packaged.cjs") return packaged;
        if (name === "./microphone-permissions.cjs") {
          return require("../../apps/desktop/electron/microphone-permissions.cjs");
        }
        throw new Error(`Unexpected import ${name}`);
      }
    });
    await new Promise(setImmediate);
    assert.equal(typeof permissionRequest, "function");
    assert.equal(typeof permissionCheck, "function");
    assert.equal(typeof permissionStatus, "function");
    assert.equal(handler({ url: "app://other/index.html" }).status, 404);
    if (scenario === "backend-missing") {
      assert.deepEqual(calls, ["backend", "error"]);
      assert.equal(app.quitCalled, true);
    } else {
      const webContents = windows[0].webContents;
      assert.equal(permissionCheck(webContents, "media", "app://yjarvis", {
        mediaType: "audio", securityOrigin: "app://yjarvis", isMainFrame: true
      }), true);
      assert.equal(permissionCheck(webContents, "media", "app://yjarvis", {
        mediaType: "video", securityOrigin: "app://yjarvis", isMainFrame: true
      }), false);
      const permissionEvent = { sender: webContents, senderFrame: webContents.mainFrame };
      assert.equal(permissionStatus(permissionEvent), "unknown");
      assert.equal(permissionStatus({ ...permissionEvent, senderFrame: { url: "https://evil.test" } }), "unknown");
      assert.deepEqual(calls, scenario === "ollama-missing"
        ? ["backend", "health", "window", "app://yjarvis/index.html"]
        : ["backend", "health", "health", "window", "app://yjarvis/index.html"]);
      const frame = { url: "app://yjarvis/index.html" };
      const event = { senderFrame: frame, sender: { mainFrame: frame } };
      const before = calls.length;
      windowControl({ ...event, senderFrame: { url: "app://yjarvis/index.html" } }, "close");
      windowControl(event, "arbitrary-command");
      frame.url = "https://other.example";
      windowControl(event, "close");
      assert.equal(calls.length, before);
      frame.url = "app://yjarvis/index.html";
      windowControl(event, "minimize");
      windowControl(event, "toggle-maximize");
      windowControl(event, "close");
      assert.deepEqual(calls.slice(before), ["minimize", "maximize", "close"]);
    }
  });
}
