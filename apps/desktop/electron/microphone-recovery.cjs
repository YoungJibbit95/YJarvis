"use strict";

const { isTrustedRenderer } = require("./microphone-permissions.cjs");

// This IPC accepts NO arbitrary URI, filename, or shell command.
// It is an OS Settings navigation only, never a permission grant.
function registerMicrophonePrivacyNavigation(ipcMain, {
  packaged, platform, shell, getWindows
}) {
  ipcMain.handle("jarvis:open-microphone-privacy-settings", async (event) => {
    const frame = event?.senderFrame;
    if (!frame || frame !== event.sender?.mainFrame ||
        !isTrustedRenderer(event.sender, frame.url, packaged, getWindows)) {
      return false;
    }
    try {
      if (platform === "win32") {
        // Microsoft documents the exact microphone Privacy Settings URI.
        await shell.openExternal("ms-settings:privacy-microphone");
        return true;
      }
      if (platform === "darwin") {
        // Fixed System Settings route; fall back to opening the application
        // if a macOS version does not recognize this deep link.
        try {
          await shell.openExternal(
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
          );
          return true;
        } catch {
          const message = await shell.openPath("/System/Applications/System Settings.app");
          return message === "";
        }
      }
      return false;
    } catch {
      return false;
    }
  });
}

module.exports = { registerMicrophonePrivacyNavigation };
