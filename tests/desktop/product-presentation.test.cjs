const assert = require("node:assert/strict");
const { test } = require("node:test");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { load } = require("./load-setup.cjs");
const { PresenceStage, runStateLabel } = load("../app/PresenceStage.tsx");
const { ActionReview } = load("../app/ActionReview.tsx");
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));

test("presence separates assistant work, microphone and dated agent events", () => {
  const idle = render(PresenceStage, { mode: "idle", microphoneActive: false });
  assert.ok(idle.includes("Im Ruhezustand") && idle.includes("Mikrofon aus"));
  assert.ok(!/Bereit|Verbunden|Letztes Agent-Ereignis/.test(idle));
  const thinking = render(PresenceStage, { mode: "thinking", microphoneActive: true,
    latestEvent: { id: "event", state: "approval_required", timestamp: "2026-10-08T12:00:00Z" } });
  for (const text of ["Anfrage aktiv", "Mikrofon aktiv", "Letztes Agent-Ereignis", "Freigabe benötigt"]) assert.ok(thinking.includes(text));
  const speaking = render(PresenceStage, { mode: "speaking", microphoneActive: false });
  assert.ok(speaking.includes("Sprachausgabe aktiv oder vorgemerkt"));
  assert.ok(!/Audiopegel|Lautstärke|hört zu/.test(speaking));
});

test("all real run states have distinct labels; unknown states stay neutral", () => {
  const states = ["received", "thinking", "approval_required", "executing", "done", "error"];
  assert.equal(new Set(states.map(runStateLabel)).size, states.length);
  assert.equal(runStateLabel("error"), "Aktion fehlgeschlagen");
  for (const unknown of ["new_state", "constructor", "toString", "__proto__"]) assert.equal(runStateLabel(unknown), "Statusmeldung");
});

function approval(tool_name, tool_input) {
  return { id: "approval-42", run_id: "run-42", session_id: "session-42", tool_name, tool_input, status: "pending", requested_at: "2026-10-08T12:00:00Z" };
}

test("approval review retains every input and raw payload, including unusual data", () => {
  const html = render(ActionReview, { approval: approval("file_write", {
    path: "C:\\Preview\\plan.txt", content: "<script>alert(1)</script>\nSecond line",
    mode: "overwrite", extra: { enabled: false, count: 0, absent: null }
  }), onDecide() {} });
  for (const text of ["Datei schreiben", "Dateipfad", "Schreibmodus", "overwrite", "extra", "false", "0", "null", "run-42", "approval-42", "Vollständige Aktionsdaten"]) assert.ok(html.includes(text));
  assert.ok(html.includes("&lt;script&gt;") && !html.includes("<script>"));
  assert.ok(!/sicher|reversibel|ungefährlich|geringes Risiko/.test(html));
});

test("unknown approval tools get a neutral fallback and empty input remains explicit", () => {
  for (const name of ["new_tool", "constructor", "__proto__"]) {
    const html = render(ActionReview, { approval: approval(name, {}), onDecide() {} });
    assert.ok(html.includes("Aktion prüfen") && html.includes(name) && html.includes("Keine Eingabedaten übermittelt"));
  }
});

test("both approval controls dispatch the existing id and exact decision", () => {
  const calls = [];
  const tree = ActionReview({ approval: approval("open_url", { url: "https://example.org" }), onDecide: (...args) => calls.push(args) });
  function buttons(node) {
    if (!node || typeof node !== "object") return [];
    if (Array.isArray(node)) return node.flatMap(buttons);
    return node.type === "button" ? [node] : buttons(node.props?.children);
  }
  const controls = buttons(tree);
  assert.deepEqual(Array.from(controls, (button) => button.props.children), ["Freigeben", "Ablehnen"]);
  controls.forEach((button) => button.props.onClick());
  assert.deepEqual(calls, [["approval-42", "approve"], ["approval-42", "deny"]]);
});
