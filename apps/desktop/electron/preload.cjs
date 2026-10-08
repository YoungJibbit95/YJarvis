const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("jarvisDesktop", {
  platform: process.platform,
  windowControls: {
    close: () => ipcRenderer.send("jarvis:window-control", "close"),
    minimize: () => ipcRenderer.send("jarvis:window-control", "minimize"),
    toggleMaximize: () => ipcRenderer.send("jarvis:window-control", "toggle-maximize")
  },
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node
  }
});
