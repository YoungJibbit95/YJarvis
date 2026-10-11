const assert = require("node:assert/strict");
const { test } = require("node:test");
const { registerMicrophonePrivacyNavigation } =
  require("../../apps/desktop/electron/microphone-recovery.cjs");

function permissionNavigation(platform, packaged = true) {
  const url = packaged ? "app://yjarvis/index.html" : "http://127.0.0.1:5173";
  const wc = { mainFrame: { url } };
  const handlers = new Map(), urls = [], paths = [];
  let failLink = false;
  const window = { webContents: wc };
  registerMicrophonePrivacyNavigation({ handle(channel, callback) { handlers.set(channel, callback); } }, {
    packaged, platform,
    shell: {
      async openExternal(value) { urls.push(value); if (failLink) throw Error("bad protocol"); },
      async openPath(value) { paths.push(value); return ""; }
    },
    getWindows: () => [window],
  });
  return {
    urls, paths, wc,
    failLink() { failLink = true; },
    async request(event = { sender: wc, senderFrame: wc.mainFrame }) {
      return handlers.get("jarvis:open-microphone-privacy-settings")(event);
    }
  };
}

test("Windows privacy settings IPC uses exactly Microsoft microphone URI", async () => {
  const p = permissionNavigation("win32");
  assert.equal(await p.request(), true);
  assert.deepEqual(p.urls, ["ms-settings:privacy-microphone"]);
  assert.deepEqual(p.paths, []);
});

test("macOS opens fixed System Settings deep link with safe app fallback", async () => {
  const p = permissionNavigation("darwin");
  assert.equal(await p.request(), true);
  assert.deepEqual(p.urls, ["x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"]);
  const deniedDeepLink = permissionNavigation("darwin");
  deniedDeepLink.failLink();
  assert.equal(await deniedDeepLink.request(), true);
  assert.deepEqual(deniedDeepLink.paths, ["/System/Applications/System Settings.app"]);
});

test("remote, non-main and unregistered sender never reach OS shell", async () => {
  const p = permissionNavigation("win32");
  assert.equal(await p.request({ sender: p.wc, senderFrame: { url: "https://evil.invalid" } }), false);
  assert.equal(await p.request({ sender: { mainFrame: { url: p.wc.mainFrame.url } }, senderFrame: p.wc.mainFrame }), false);
  const frame = { url: p.wc.mainFrame.url };
  assert.equal(await p.request({ sender: p.wc, senderFrame: frame }), false);
  assert.deepEqual(p.urls, []);
});

test("Linux cannot open unrelated system services via this IPC", async () => {
  const p = permissionNavigation("linux", false);
  assert.equal(await p.request(), false);
  assert.deepEqual(p.urls, []);
});
