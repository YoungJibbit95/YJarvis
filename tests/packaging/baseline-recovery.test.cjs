"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");

test("existing development and packaging scripts remain real commands", () => {
  const pkg = JSON.parse(read("package.json"));
  const expected = {
    "test:packaging": "node --test tests/packaging/*.test.cjs",
    "test:packaged-backend": "node scripts/smoke-packaged-backend.mjs",
    "dev:agent": "node scripts/dev.mjs agent",
    "dev:agent:reload": "node scripts/dev.mjs agent-reload",
    "test:startup": "node --test tests/startup/startup.test.cjs",
    "dist:mac": "cd apps/desktop && node package-mac.mjs",
    "dist:win": "node scripts/package-windows.mjs"
  };
  for (const [name, command] of Object.entries(expected)) {
    assert.equal(pkg.scripts[name], command, `missing or altered script: ${name}`);
  }
  for (const filename of [
    "tests/packaging/packaged.test.cjs",
    "tests/startup/startup.test.cjs",
    "scripts/smoke-packaged-backend.mjs",
    "scripts/dev.mjs",
    "scripts/package-windows.mjs",
    "apps/desktop/package-mac.mjs"
  ]) {
    assert.ok(fs.statSync(path.join(root, filename)).isFile(), `script target missing: ${filename}`);
  }
});

test("detached PR34 component prototypes cannot silently become production imports", () => {
  const config = JSON.parse(read("apps/desktop/tsconfig.json"));
  assert.deepEqual(config.include, ["src"]);
  assert.deepEqual(config.exclude, ["src/components"]);
  const src = path.join(root, "apps", "desktop", "src");
  let inspected = 0;
  const scan = (directory) => {
    for (const dirent of fs.readdirSync(directory, { withFileTypes: true })) {
      const filename = path.join(directory, dirent.name);
      if (dirent.isDirectory()) {
        if (directory === src && dirent.name === "components") continue;
        scan(filename);
      } else if (/\.(tsx?|jsx?)$/.test(dirent.name)) {
        inspected++;
        assert.doesNotMatch(fs.readFileSync(filename, "utf8"),
          /(?:from\s*|import\s*\()\s*["'][^"']*\/components\//,
          `experimental component imported by production: ${path.relative(root, filename)}`);
      }
    }
  };
  scan(src);
  assert.ok(inspected > 10, "expected to inspect actual renderer source files");
});
