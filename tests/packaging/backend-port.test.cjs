const test = require("node:test");
const assert = require("node:assert/strict");
const net = require("node:net");
const { checkBackendPort, startPackagedBackend } = require("../../apps/desktop/electron/packaged.cjs");

test("a conflicting backend prevents spawn rather than reusing another app's settings", async () => {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  let spawned = false;
  try {
    await assert.rejects(startPackagedBackend({ start() { spawned = true; } }, "resources", "data", {}, () => checkBackendPort(port)), /bereits verwendet/);
    assert.equal(spawned, false);
    assert.equal(server.listening, true);
  } finally { await new Promise(resolve => server.close(resolve)); }
  await checkBackendPort(port);
});
