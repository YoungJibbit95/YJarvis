const assert = require("node:assert/strict");
const { test } = require("node:test");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { load } = require("./load-setup.cjs");
const { parseAcceleratorProfile } = load("acceleratorProfile.ts");
const { AcceleratorProfileContent } = load("AcceleratorProfileView.tsx", { "../api": {
  fetchAcceleratorProfile() { throw new Error("Presentation must not fetch"); }
} });
const adapter = () => ({ display_name: "Adapter α", dedicated_video_memory_bytes: 8 * 1024 ** 3,
  shared_system_memory_bytes: 16 * 1024 ** 3, classification: "hardware" });
const fixture = () => ({ status: "available", adapters: [adapter()] });
const render = (state) => renderToStaticMarkup(React.createElement(AcceleratorProfileContent, { state, onRetry() {} }));
const show = (value) => render({ status: "loaded", profile: parseAcceleratorProfile(value) });

test("multiple native adapters, software and memory semantics are informational", () => {
  const html = show({ status: "available", adapters: [adapter(), { ...adapter(), display_name: "Basic Render", classification: "software" }] });
  for (const text of ["Adapter α", "Basic Render", "Hardware-Adapter", "Software-Adapter", "8 GiB", "16 GiB", "Obergrenze", "kein zusätzlicher dedizierter Grafikspeicher"]) assert.ok(html.includes(text));
  assert.equal((html.match(/<li>/g) || []).length, 2);
  assert.ok(!/<button|<a\b|Empfohlen|Optimal|Schnell|Installieren|Herunterladen|Balanced|Qwen|Whisper|TOPS|CUDA/.test(html));
});

test("unknown memory and zero stay distinct without inventing adapter classification", () => {
  const html = show({ status: "available", adapters: [{ ...adapter(), classification: "unknown", dedicated_video_memory_bytes: 0, shared_system_memory_bytes: null }] });
  for (const text of ["0 GiB", "<dd>Unbekannt</dd>", "Adaptertyp unbekannt"]) assert.ok(html.includes(text));
  assert.ok(show({ status: "available", adapters: [{ ...adapter(), dedicated_video_memory_bytes: 1 }] }).includes("&lt; 0,1 GiB"));
  assert.equal(parseAcceleratorProfile({ status: "available", adapters: [{ ...adapter(), dedicated_video_memory_bytes: Number.MAX_SAFE_INTEGER }] }).adapters[0].dedicated_video_memory_bytes, Number.MAX_SAFE_INTEGER);
});

test("empty, unsupported, unknown, transport error and loading are distinct", () => {
  assert.ok(show({ status: "available", adapters: [] }).includes("Windows meldet keine Grafikadapter"));
  assert.ok(show({ status: "unsupported", adapters: [] }).includes("noch nicht unterstützt"));
  assert.ok(!show({ status: "unsupported", adapters: [] }).includes("Windows"));
  assert.ok(render({ status: "loading" }).includes('role="status"'));
  for (const html of [render({ status: "error" }), show({ status: "unknown", adapters: [] })]) {
    assert.ok(html.includes('role="alert"') && html.includes("Grafikdetails erneut lesen"));
    assert.ok(html.includes("Systemdaten, Modellübersicht und Einrichtungsstatus bleiben unverändert"));
    assert.ok(!/GiB|<li>|Installieren|Empfohlen/.test(html));
  }
});

for (const field of ["dedicated_video_memory_bytes", "shared_system_memory_bytes"]) {
  for (const value of [-1, Number.MAX_SAFE_INTEGER + 1, 0.5, true, "8", Infinity, NaN, undefined]) {
    test(`reject ${field}: ${value}`, () => assert.throws(() => parseAcceleratorProfile({ status: "available", adapters: [{ ...adapter(), [field]: value }] })));
  }
}

test("strict nested DTO rejects malformed, missing, extra, contradictory and oversized values", () => {
  for (const value of [null, [], "profile", {}, { ...fixture(), score: 9 }, { ...fixture(), status: "fast" },
    { status: "unknown", adapters: [adapter()] }, { status: "unsupported", adapters: [adapter()] },
    { status: "available", adapters: {} }, { status: "available", adapters: Array(65).fill(adapter()) }]) {
    assert.throws(() => parseAcceleratorProfile(value));
  }
  for (const value of [null, [], {}, { ...adapter(), vendor: "guessed" }, { ...adapter(), classification: "NVIDIA" },
    ...["", "  ", "x".repeat(129), 123].map((display_name) => ({ ...adapter(), display_name }))]) {
    assert.throws(() => parseAcceleratorProfile({ status: "available", adapters: [value] }));
  }
  for (const key of Object.keys(adapter())) {
    const item = adapter(); delete item[key];
    assert.throws(() => parseAcceleratorProfile({ status: "available", adapters: [item] }));
  }
  for (const key of Object.keys(fixture())) {
    const value = fixture(); delete value[key];
    assert.throws(() => parseAcceleratorProfile(value));
  }
});

test("display name is escaped and cannot become an action", () => {
  const html = show({ status: "available", adapters: [{ ...adapter(), display_name: '<button onclick="attack()">Name</button>' }] });
  assert.ok(html.includes("&lt;button"));
  assert.ok(!html.includes("<button"));
});
