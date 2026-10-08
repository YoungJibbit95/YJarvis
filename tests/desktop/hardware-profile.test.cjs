const assert = require("node:assert/strict");
const { test } = require("node:test");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { load } = require("./load-setup.cjs");
const { parseHardwareProfile } = load("hardwareProfile.ts");
const { HardwareProfileContent } = load("HardwareProfileView.tsx", { "../api": {
  fetchHardwareProfile() { throw new Error("Presentation must not fetch"); }
}, "./AcceleratorProfileView": { AcceleratorProfileView: () => null } });

const fixture = () => ({ platform: "windows", architecture: "x86_64", logical_cpu_count: 12,
  total_memory_bytes: 32 * 1024 ** 3, available_storage_bytes: 420 * 1024 ** 3,
  storage_path_scope: "app_runtime_directory" });
const render = (state) => renderToStaticMarkup(React.createElement(HardwareProfileContent, { state, onRetry() {} }));

test("normalized platforms/architectures and nullable values validate", () => {
  for (const platform of ["windows", "macos", "linux", "unknown"]) {
    for (const architecture of ["x86_64", "arm64", "other", "unknown"]) {
      const input = { ...fixture(), platform, architecture, logical_cpu_count: null, total_memory_bytes: null, available_storage_bytes: null };
      assert.deepEqual(JSON.parse(JSON.stringify(parseHardwareProfile(input))), input);
    }
  }
  assert.equal(parseHardwareProfile({ ...fixture(), available_storage_bytes: 0 }).available_storage_bytes, 0);
});

for (const [field, values] of Object.entries({
  platform: ["Windows", null, 1], architecture: ["AMD64", null], storage_path_scope: ["models", null],
  logical_cpu_count: [0, -1, 1.5, true, "12", Number.MAX_SAFE_INTEGER + 1, undefined],
  total_memory_bytes: [0, -1, 1.5, false, "32", Infinity, undefined],
  available_storage_bytes: [-1, 1.5, true, "420", NaN, undefined]
})) for (const value of values) test(`reject ${field}: ${value}`, () => {
  assert.throws(() => parseHardwareProfile({ ...fixture(), [field]: value }));
});

test("reject missing fields, extra future fields and nonobjects", () => {
  for (const value of [null, [], "hardware", {}, { ...fixture(), gpu: "fast" }]) assert.throws(() => parseHardwareProfile(value));
  for (const key of Object.keys(fixture())) {
    const value = fixture(); delete value[key];
    assert.throws(() => parseHardwareProfile(value));
  }
});

test("known values are informational, with binary units and explicit storage scope", () => {
  const html = render({ status: "loaded", profile: parseHardwareProfile(fixture()) });
  for (const text of ["Windows", "x86-64", "12", "32 GiB", "420 GiB", "App-Datenstandort", "App-Datenordner"]) assert.ok(html.includes(text));
  assert.ok(!/<button|<a\b|Empfohlen|Installieren|Herunterladen|Balanced|Qwen|Whisper/.test(html));
});

test("unknown values have no invented numbers; real zero free space remains distinct", () => {
  const input = { ...fixture(), platform: "unknown", architecture: "unknown", logical_cpu_count: null, total_memory_bytes: null, available_storage_bytes: null };
  const html = render({ status: "loaded", profile: parseHardwareProfile(input) });
  assert.equal((html.match(/<dd>Unbekannt<\/dd>/g) || []).length, 5);
  assert.ok(!/GiB|<dd>0/.test(html));
  assert.ok(render({ status: "loaded", profile: { ...input, available_storage_bytes: 0 } }).includes("0 GiB"));
  assert.ok(render({ status: "loaded", profile: { ...input, available_storage_bytes: 1 } }).includes("&lt; 0,1 GiB"));
});

test("loading/error are confined to hardware; retry has no catalog/readiness callback", () => {
  const loading = render({ status: "loading" });
  const error = render({ status: "error" });
  assert.ok(loading.includes('role="status"'));
  assert.ok(error.includes('role="alert"') && error.includes("Systemdaten erneut lesen"));
  assert.ok(error.includes("Modellübersicht und Einrichtungsstatus bleiben unverändert"));
  assert.ok(!error.includes("hardware-facts"));
});
