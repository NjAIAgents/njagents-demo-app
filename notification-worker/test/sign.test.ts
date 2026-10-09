import { test } from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { signPayload, type WebhookEndpoint } from "../src/webhooks/sign";

const v1: WebhookEndpoint = {
  id: "ep_1",
  accountId: "acct_1",
  url: "https://receiver.example/hooks",
  schema: "v1",
  auth: { signingSecret: "whsec_test_v1" },
};

test("signs a v1 endpoint payload so the receiver can verify it", () => {
  const signed = signPayload(v1, { id: "evt_1", type: "approval.decided" });
  assert.equal(signed.body, JSON.stringify({ id: "evt_1", type: "approval.decided" }));
  const expected = createHmac("sha256", "whsec_test_v1")
    .update(`${signed.timestamp}.${signed.body}`)
    .digest("hex");
  assert.equal(signed.signature, `t1=${expected}`);
});
