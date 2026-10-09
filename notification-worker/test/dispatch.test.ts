import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { dispatchWebhook, MAX_ATTEMPTS, type WebhookEvent } from "../src/webhooks/dispatch";
import type { WebhookEndpoint } from "../src/webhooks/sign";
import { scheduled } from "../src/queue/retry";
import { dead } from "../src/queue/deadLetter";
import { resetLog } from "../src/logger";

const endpoint: WebhookEndpoint = {
  id: "ep_1",
  accountId: "acct_1",
  url: "https://receiver.example/hooks",
  schema: "v1",
  auth: { signingSecret: "whsec_test_v1" },
};

const event: WebhookEvent = {
  id: "evt_1",
  type: "approval.decided",
  accountId: "acct_1",
  occurredAt: "2026-10-01T12:00:00Z",
  data: { requestId: "R-1" },
};

const realFetch = globalThis.fetch;

function respondWith(status: number) {
  globalThis.fetch = (async () => new Response(null, { status })) as typeof fetch;
}

beforeEach(() => {
  scheduled.length = 0;
  dead.length = 0;
  resetLog();
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

test("a 2xx response is a delivery", async () => {
  respondWith(204);
  const result = await dispatchWebhook(endpoint, event);
  assert.deepEqual(result, { delivered: true, status: 204, attempt: 1 });
  assert.equal(scheduled.length, 0);
});

test("a 5xx response is retried on the schedule", async () => {
  respondWith(503);
  const result = await dispatchWebhook(endpoint, event);
  assert.equal(result.delivered, false);
  assert.deepEqual(scheduled, [{ endpointId: "ep_1", eventId: "evt_1", attempt: 2, delayS: 30 }]);
});

test("the last failed attempt goes to the dead-letter queue", async () => {
  respondWith(500);
  await dispatchWebhook(endpoint, event, MAX_ATTEMPTS);
  assert.equal(scheduled.length, 0);
  assert.equal(dead.length, 1);
  assert.match(dead[0].reason, /status 500 after 5 attempts/);
});
