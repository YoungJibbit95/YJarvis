const { readFileSync } = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

// Use the committed TypeScript toolchain; no added test framework/dependency.
function load(file, mocks = {}, globals = {}) {
  const filename = path.resolve(__dirname, "../../apps/desktop/src/setup", file);
  const code = ts.transpileModule(readFileSync(filename, "utf8"), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020
  } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, require: (name) => mocks[name] ?? require(name), URL, Date, Intl, ...globals }, { filename });
  return exports;
}

module.exports = { load };
