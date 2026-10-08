const test = require("node:test");
const assert = require("node:assert/strict");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { load } = require("./load-setup.cjs");
const { parseInstallState, parseInstallOptions } = load("installTypes.ts");

test("installation status preserves interruption and rejects invented progress", () => {
  const valid = { status: "interrupted", id: "job", stage: "Download", completed: 10, total: null, error: "restart" };
  assert.equal(parseInstallState(valid).status, "interrupted");
  for (const change of [{ status: "ready" }, { completed: -1 }, { completed: Infinity }, { total: -1 }, { error: {} }, { configured_fields: false }, { configured_fields: ["allowed_paths"] }]) {
    assert.throws(() => parseInstallState({ ...valid, ...change }));
  }
  assert.throws(() => parseInstallOptions({ whisper_models: [1], voices: [] }));
});

test("walkthrough offers individual and complete installs with accessible selections", () => {
  const calls = [];
  const hooks = { ...React, useState: value => [value, () => {}], useEffect() {}, useRef: value => ({ current: value }) };
  const { GuidedInstaller } = load("GuidedInstaller.tsx", {
    react: hooks,
    "../api": { setupInstallation: async (action, selection) => { calls.push({ action, selection }); return { status: "running" }; } }
  });
  const tree = GuidedInstaller({ onConfigured() {} });
  const html = renderToStaticMarkup(tree);
  for (const label of ["Chat-Modell installieren", "Spracheingabe installieren", "Stimme installieren", "Auswahl installieren", "install-chat", "install-whisper", "install-voice"]) assert.ok(html.includes(label));
  function buttons(node) {
    if (!node || typeof node !== "object") return [];
    if (Array.isArray(node)) return node.flatMap(buttons);
    return node.type === "button" ? [node] : buttons(node.props?.children);
  }
  buttons(tree).find(button => button.props.children === "Stimme installieren").props.onClick();
  assert.equal(calls[0].action, "start");
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0].selection)), { chat_model: null, whisper_model: null, voice: "de_DE-thorsten-medium", install_ollama: false });
});
