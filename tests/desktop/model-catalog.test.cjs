const assert = require("node:assert/strict");
const { test } = require("node:test");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

const { load } = require("./load-setup.cjs");
const { parseModelCatalog } = load("modelCatalog.ts");
const { ModelCatalogContent } = load("ModelCatalogBrowser.tsx", { "../api": {
  fetchModelCatalog() { throw new Error("Presentation must not fetch"); }
} });

// Synthetic contract fixtures, never a second copy of the bundled model data.
function fixture() {
  const source = { publisher: "Fixture publisher", url: "https://example.org/model", checked_on: "2026-10-08" };
  return { entries: ["chat", "speech_to_text", "text_to_speech"].map((category, index) => ({
    id: `fixture-${index}`, category, display_name: `Fixture ${index}`, publisher: "Fixture publisher",
    model_id: `publisher/fixture-${index}`, description: "Synthetic metadata for contract tests.", source,
    licenses: [{ name: index === 2 ? null : "Fixture license", scope: "model", source },
      ...(index === 2 ? [{ name: "Fixture dataset license", scope: "dataset", source }] : [])],
    runtime: { backend: ["ollama", "whisper_cpp", "piper"][index], model_id: `fixture-${index}` },
    acquisition: { mechanism: index === 0 ? "ollama_library" : "hugging_face_files",
      source: { ...source, url: index === 0 ? "https://ollama.com/library/fixture" : "https://huggingface.co/fixture" },
      approximate_download_bytes: index === 2 ? null : 488000000 },
    context_window_tokens: index === 0 ? 32768 : null, publisher_quality_label: null
  })) };
}

test("valid categories and unknown metadata survive validation; data is copied", () => {
  const input = fixture();
  const result = parseModelCatalog(input);
  assert.deepEqual(JSON.parse(JSON.stringify(result)), input.entries);
  input.entries[0].runtime.model_id = "mutated";
  assert.equal(result[0].runtime.model_id, "fixture-0");
});

const badData = [
  ["empty catalog", (data) => { data.entries = []; }],
  ["missing entries", (data) => { delete data.entries; }],
  ["unknown field", (data) => { data.recommended = true; }],
  ["duplicate catalog ID", (data) => { data.entries[1].id = data.entries[0].id; }],
  ["duplicate backend/model", (data) => { data.entries.push({ ...data.entries[0], id: "different" }); }],
  ...[
    ["category", "image"], ["id", "Bad ID"], ["display_name", ""], ["publisher", 1],
    ["context_window_tokens", -1], ["context_window_tokens", "32768"], ["context_window_tokens", 1.5],
    ["context_window_tokens", Number.MAX_SAFE_INTEGER + 1], ["licenses", []], ["licenses", null],
    ["source", null], ["publisher_quality_label", false]
  ].map(([key, value]) => [`invalid ${key}: ${value}`, (data) => { data.entries[0][key] = value; }]),
  ["unknown backend", (data) => { data.entries[0].runtime.backend = "new-backend"; }],
  ["wrong category/backend pair", (data) => { data.entries[0].runtime.backend = "piper"; }],
  ["unknown acquisition", (data) => { data.entries[0].acquisition.mechanism = "shell"; }],
  ["wrong acquisition host", (data) => { data.entries[0].acquisition.source.url = "https://example.org"; }],
  ["invalid size", (data) => { data.entries[0].acquisition.approximate_download_bytes = true; }],
  ["missing size", (data) => { delete data.entries[0].acquisition.approximate_download_bytes; }],
  ["missing licenses", (data) => { delete data.entries[0].licenses; }],
  ["unknown license scope", (data) => { data.entries[0].licenses[0].scope = "backend"; }],
  ["duplicate license scope", (data) => { data.entries[0].licenses.push(data.entries[0].licenses[0]); }],
  ["missing model license scope", (data) => { data.entries[0].licenses[0].scope = "dataset"; }],
  ["missing license source", (data) => { delete data.entries[0].licenses[0].source; }],
  ["missing source", (data) => { delete data.entries[0].source; }],
  ["invalid date", (data) => { data.entries[0].source.checked_on = "2026-02-30"; }],
  ["invalid URL", (data) => { data.entries[0].source.url = "javascript:alert(1)"; }],
  ["credential URL", (data) => { data.entries[0].source.url = "https://user:pass@example.org"; }],
  ["non-chat context", (data) => { data.entries[1].context_window_tokens = 100; }]
];
for (const [name, mutate] of badData) test(`reject ${name}`, () => {
  const data = fixture();
  mutate(data);
  assert.throws(() => parseModelCatalog(data));
});

test("presentation distinguishes categories, license scopes and unknown model license", () => {
  const html = renderToStaticMarkup(React.createElement(ModelCatalogContent, {
    state: { status: "loaded", entries: parseModelCatalog(fixture()) }, onRetry() {}
  }));
  for (const label of ["Chat", "Spracheingabe", "Sprachausgabe", "Modelllizenz", "Datensatzlizenz", "Nicht eindeutig angegeben", "32.768"]) assert.ok(html.includes(label));
  assert.equal((html.match(/Downloadgröße/g) || []).length, 2);
  assert.ok(!/<a\b|<button\b|onclick|Installieren|Herunterladen|Empfohlen/.test(html));
});

test("loading and browse error are explicit without a readiness mutation callback", () => {
  const loading = renderToStaticMarkup(React.createElement(ModelCatalogContent, { state: { status: "loading" }, onRetry() {} }));
  const error = renderToStaticMarkup(React.createElement(ModelCatalogContent, { state: { status: "error" }, onRetry() {} }));
  assert.ok(loading.includes('role="status"') && loading.includes("wird geladen"));
  assert.ok(error.includes('role="alert"') && error.includes("Einrichtungsstatus bleibt unverändert"));
  assert.ok(error.includes("Modellübersicht erneut laden"));
  assert.ok(!error.includes("catalog-card"));
});
