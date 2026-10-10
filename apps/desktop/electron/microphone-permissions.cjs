"use strict";

// Pure, testable Electron 33 permission boundary. The OS remains authoritative.
function isTrustedRenderer(webContents, requestedUrl, packaged, getWindows) {
  if (!webContents || !requestedUrl) return false;
  const window = getWindows().find((item) => item.webContents === webContents);
  if (!window || !webContents.mainFrame) return false;
  try {
    const top = new URL(webContents.mainFrame.url);
    const request = new URL(requestedUrl);
    if (packaged) {
      return top.protocol === "app:" && top.host === "yjarvis" &&
        request.protocol === "app:" && request.host === "yjarvis" &&
        !top.username && !top.password && !request.username && !request.password;
    }
    const dev = "http://127.0.0.1:5173";
    return top.origin === dev && request.origin === dev;
  } catch {
    return false;
  }
}

function nativeMicStatus(platform, systemPreferences) {
  if (platform !== "darwin" && platform !== "win32") return "unknown";
  try { return systemPreferences.getMediaAccessStatus("microphone"); }
  catch { return "unknown"; }
}

function installMicrophonePermissions(ses, {
  packaged, platform, systemPreferences, getWindows
}) {
  function trusted(contents, url) {
    return isTrustedRenderer(contents, url, packaged, getWindows);
  }
  function osAllows() {
    return !["denied", "restricted"].includes(nativeMicStatus(platform, systemPreferences));
  }

  ses.setPermissionCheckHandler((contents, permission, requestingOrigin, details = {}) => {
    if (permission !== "media" || details.mediaType !== "audio" || !osAllows()) return false;
    return trusted(contents, details.requestingUrl || details.securityOrigin || requestingOrigin) &&
      (!details.securityOrigin || trusted(contents, details.securityOrigin)) &&
      details.isMainFrame !== false;
  });

  ses.setPermissionRequestHandler((contents, permission, callback, details = {}) => {
    const mediaTypes = details.mediaTypes;
    if (permission !== "media" || !Array.isArray(mediaTypes) ||
        mediaTypes.length !== 1 || mediaTypes[0] !== "audio" ||
        !trusted(contents, details.requestingUrl) || !osAllows()) {
      callback(false);
      return;
    }
    if (platform !== "darwin") {
      // Chromium's approval does NOT prove Windows privacy/access is granted.
      callback(true);
      return;
    }
    // Only reached as a consequence of a renderer getUserMedia request,
    // never at app startup. macOS TCC denial/restriction is authoritative.
    const native = nativeMicStatus(platform, systemPreferences);
    if (native === "granted") { callback(true); return; }
    if (native === "denied" || native === "restricted") { callback(false); return; }
    Promise.resolve().then(() => systemPreferences.askForMediaAccess("microphone"))
      .then((granted) => callback(granted === true && osAllows()))
      .catch(() => callback(false));
  });
}

module.exports = { installMicrophonePermissions, isTrustedRenderer, nativeMicStatus };
