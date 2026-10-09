const { test } = require("node:test");
const assert = require("node:assert/strict");
const health = require("../health");
const { version } = require("../../version.json");

function fakeRes() {
  const res = { statusCode: 0, body: undefined };
  res.status = (code) => ((res.statusCode = code), res);
  res.json = (body) => ((res.body = body), res);
  return res;
}

test("health reports the deployed version", () => {
  const res = fakeRes();
  health({}, res);
  assert.equal(res.statusCode, 200);
  assert.deepEqual(res.body, { ok: true, service: "approvals-api", version });
});
