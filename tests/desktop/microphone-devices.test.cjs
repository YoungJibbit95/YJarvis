const assert = require("node:assert/strict");
const { test } = require("node:test");
const { load } = require("./load-setup.cjs");

function helper(window = {}) {
  return load("../voice/microphoneDevices.ts", {}, { window });
}

test("audio device selection excludes cameras, default aliases and unnamed phantom IDs", () => {
  const mic = helper();
  const options = mic.microphoneDeviceOptions([
    { kind: "videoinput", deviceId: "cam", label: "Kamera" },
    { kind: "audioinput", deviceId: "default", label: "Default" },
    { kind: "audioinput", deviceId: "communications", label: "Communication" },
    { kind: "audioinput", deviceId: "", label: "" },
    { kind: "audioinput", deviceId: "mic-1", label: "" },
    { kind: "audioinput", deviceId: "mic-2", label: "USB Audio" },
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(options)), [
    { id: "mic-1", label: "Mikrofon 1 (Name durch Betriebssystem verborgen)" },
    { id: "mic-2", label: "USB Audio" }
  ]);
});

test("selected physical device is passed as exact, never with silent fallback", () => {
  const mic = helper();
  const explicit = JSON.parse(JSON.stringify(mic.microphoneConstraints("usb-id")));
  assert.equal(explicit.audio.deviceId.exact, "usb-id");
  assert.equal(explicit.video, false);
  assert.equal(explicit.audio.echoCancellation, true);
  assert.equal(mic.microphoneConstraints("").audio.deviceId, undefined);
});

test("microphone preference uses local desktop storage and tolerates failures", () => {
  const values = new Map();
  const mic = helper({
    localStorage: {
      getItem(key) { return values.get(key) || null; },
      setItem(key, val) { values.set(key, val); }
    }
  });
  assert.equal(mic.readMicrophonePreference(), "");
  mic.persistMicrophonePreference("usb-id");
  assert.equal(mic.readMicrophonePreference(), "usb-id");
  const inaccessible = helper({ localStorage: { getItem() { throw Error("no"); }, setItem() { throw Error("no"); } } });
  assert.equal(inaccessible.readMicrophonePreference(), "");
  assert.doesNotThrow(() => inaccessible.persistMicrophonePreference("mic-2"));
});

test("actionable platform permission, missing-device and busy-device errors", () => {
  const mic = helper();
  assert.match(mic.microphoneErrorMessage({ name: "NotAllowedError" }, "win32"), /Windows 11/);
  assert.match(mic.microphoneErrorMessage({ name: "NotAllowedError" }, "darwin"), /macOS/);
  assert.match(mic.microphoneErrorMessage({ name: "OverconstrainedError" }, "win32"), /kein automatischer Wechsel/);
  assert.match(mic.microphoneErrorMessage({ name: "NotReadableError" }, "win32"), /belegt/);
});

test("RMS is computed from actual signed audio sample deviations", () => {
  const mic = helper();
  assert.equal(mic.audioRms(new Uint8Array([128, 128, 128])), 0);
  assert.ok(mic.audioRms(new Uint8Array([128, 190, 66])) > 0.3);
});
