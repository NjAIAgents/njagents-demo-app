// Delivers one webhook event to one customer endpoint.
//
// Retry policy: a non-2xx response or a network error is retried with backoff (see
// RETRY_SCHEDULE_S), up to MAX_ATTEMPTS. After the last attempt the event goes to the
// dead-letter queue so support can replay it.
//
// Errors raised before the HTTP call (signing, payload building) are logged by the
// outer handler in dispatchWebhook, so one malformed event cannot stall the
// consumer batch.
//
// Delivery state is recorded by the queue layer (retry.ts, deadLetter.ts).

import { signPayload, WebhookEndpoint } from "./sign";
import { deadLetter } from "../queue/deadLetter";
import { scheduleRetry } from "../queue/retry";
import { logger } from "../logger";

export const MAX_ATTEMPTS = 5;
export const RETRY_SCHEDULE_S = [30, 120, 600, 1800, 3600];
const TIMEOUT_MS = 10_000;

export interface WebhookEvent {
  id: string;
  type: "approval.decided" | "request.created" | "document.signed" | "settlement.ready";
  accountId: string;
  occurredAt: string;
  data: Record<string, unknown>;
}

export interface DeliveryResult {
  delivered: boolean;
  status?: number;
  attempt: number;
}

async function post(url: string, body: string, headers: Record<string, string>): Promise<number> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { method: "POST", body, headers, signal: controller.signal });
    return res.status;
  } finally {
    clearTimeout(timer);
  }
}

function envelope(event: WebhookEvent) {
  return {
    id: event.id,
    type: event.type,
    created: event.occurredAt,
    data: event.data,
  };
}

async function attemptDelivery(
  endpoint: WebhookEndpoint,
  event: WebhookEvent,
  attempt: number,
): Promise<DeliveryResult> {
  let status: number;
  try {
    const signed = signPayload(endpoint, envelope(event));
    status = await post(endpoint.url, signed.body, {
      "Content-Type": "application/json",
      "X-Njagents-Signature": signed.signature,
      "X-Njagents-Timestamp": String(signed.timestamp),
      "X-Njagents-Event": event.type,
    });
  } catch (err) {
    // Network errors are retried like 5xx responses.
    if ((err as Error).name === "AbortError" || (err as any).code === "ECONNRESET") {
      status = 504;
    } else {
      throw err;
    }
  }

  if (status >= 200 && status < 300) {
    logger.info("webhook delivered", {
      event: event.type, account: event.accountId, endpoint_id: endpoint.id, status,
      schema: endpoint.schema,
    });
    return { delivered: true, status, attempt };
  }

  if (attempt < MAX_ATTEMPTS) {
    logger.warn("webhook delivery failed, will retry", {
      account: event.accountId, endpoint_id: endpoint.id, status, attempt,
      next_retry_s: RETRY_SCHEDULE_S[attempt - 1],
    });
    await scheduleRetry(endpoint, event, attempt + 1, RETRY_SCHEDULE_S[attempt - 1]);
  } else {
    await deadLetter(endpoint, event, `status ${status} after ${attempt} attempts`);
  }
  return { delivered: false, status, attempt };
}

export async function dispatchWebhook(
  endpoint: WebhookEndpoint,
  event: WebhookEvent,
  attempt = 1,
): Promise<DeliveryResult> {
  try {
    return await attemptDelivery(endpoint, event, attempt);
  } catch (err) {
    // Keep the batch moving: log and skip this event.
    logger.error("webhook dispatch error", {
      account: event.accountId, endpoint_id: endpoint.id, event: event.type,
      schema: endpoint.schema, error: err,
    });
    logger.error("webhook dropped, not retried", {
      account: event.accountId, endpoint_id: endpoint.id, event: event.type,
      reason: "dispatch_error",
    });
    return { delivered: false, attempt };
  }
}
