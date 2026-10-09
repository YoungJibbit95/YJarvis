const assert = require("node:assert/strict");
const { test } = require("node:test");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const {
  installMicrophonePermissions, isTrustedRenderer, nativeMicStatus
} = require("../../apps/desktop/electron/microphone-permissions.cjs");

function harness({ packaged = true, platform = "win32", status = "granted" } = {}) {
  const url = packaged ? "app://yjarvis/index.html" : "http://127.0.0.1:5173";
  const contents = { mainFrame: { url } };
  const ses = {
    setPermissionCheckHandler(fn) { this.check = fn; },
    setPermissionRequestHandler(fn) { this.request = fn; }
  };
  let prompts = 0, native = status;
  const systemPreferences = {
    getMediaAccessStatus: () => native,
    async askForMediaAccess() { prompts++; return native !== "denied"; }
  };
  const windows = [{ webContents: contents }];
  installMicrophonePermissions(ses, {
    packaged, platform, systemPreferences, getWindows: () => windows
  });
  return {
    ses, contents, windows, url, systemPreferences,
    setNative(value) { native = value; },
    prompts: () => prompts,
    request(permission, mediaTypes, requestingUrl = url) {
      return new Promise(resolve => ses.request(contents, permission, resolve, { mediaTypes, requestingUrl }));
    },
    check(permission, mediaType, origin = url) {
      return ses.check(contents, permission, origin,
        { mediaType, isMainFrame: true, securityOrigin: origin, requestingUrl: origin });
    },
  };
}

test("packaged app://yjarvis and exact local development renderer may request audio", async () => {
  for (const packaged of [true, false]) {
    const h = harness({ packaged });
    assert.equal(h.check("media", "audio"), true);
    assert.equal(await h.request("media", ["audio"]), true);
    assert.equal(h.prompts(), 0);
    assert.equal(h.check("media", "video"), false);
    assert.equal(await h.request("media", ["video"]), false);
    assert.equal(await h.request("media", ["audio", "video"]), false);
    assert.equal(await h.request("display-capture", ["audio"]), false);
    assert.equal(await h.request("geolocation", []), false);
  }
});

test("remote origins, malicious top frames and non-main frames are blocked", async () => {
  const h = harness();
  for (const host of [
    "https://evil.example", "app://attacker/index.html",
    "http://127.0.0.1:5173", "app://yjarvis.evil/index.html",
  ]) {
    assert.equal(h.check("media", "audio", host), false);
    assert.equal(await h.request("media", ["audio"], host), false);
  }
  assert.equal(h.ses.check(h.contents, "media", h.url,
    { mediaType: "audio", isMainFrame: false, securityOrigin: h.url }), false);
  const unregistered = { mainFrame: { url: h.url } };
  assert.equal(h.ses.check(unregistered, "media", h.url,
    { mediaType: "audio", isMainFrame: true, securityOrigin: h.url }), false);
  assert.equal(isTrustedRenderer(null, h.url, true, () => h.windows), false);
  assert.equal(h.ses.check(h.contents, "media", h.url, {}), false);
});

test("native microphone denial/restriction is not overridden by Electron", async () => {
  for (const platform of ["win32", "darwin"]) {
    for (const native of ["denied", "restricted"]) {
      const h = harness({ platform, status: native });
      assert.equal(h.check("media", "audio"), false);
      assert.equal(await h.request("media", ["audio"]), false);
      assert.equal(h.prompts(), 0);
    }
  }
});

test("macOS TCC prompt only follows an explicit trusted audio request", async () => {
  const h = harness({ platform: "darwin", status: "not-determined" });
  assert.equal(h.prompts(), 0);
  assert.equal(await h.request("media", ["video"]), false);
  assert.equal(h.prompts(), 0);
  assert.equal(await h.request("media", ["audio"]), true);
  assert.equal(h.prompts(), 1);
  h.setNative("denied");
  assert.equal(await h.request("media", ["audio"]), false);
  assert.equal(h.prompts(), 1);
});

test("dev origin is intentionally restricted to loaded loopback address", async () => {
  const h = harness({ packaged: false });
  assert.equal(h.check("media", "audio", "http://localhost:5173"), false);
  assert.equal(await h.request("media", ["audio"], "https://127.0.0.1:5173"), false);
  h.contents.mainFrame.url = "http://remote.example";
  assert.equal(await h.request("media", ["audio"]), false);
});

test("macOS bundle includes microphone usage description but does not grant camera access", () => {
  const source = readFileSync(path.join(__dirname, "../../apps/desktop/electron-builder.cjs"), "utf8");
  assert.match(source, /NSMicrophoneUsageDescription/);
  assert.doesNotMatch(source, /NSCameraUsageDescription/);
  assert.equal(nativeMicStatus("win32", { getMediaAccessStatus: () => "unknown" }), "unknown");
});
