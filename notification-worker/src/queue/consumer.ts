// Pulls webhook events off the `webhooks` topic in batches and dispatches each one to
// every active endpoint registered for the event's account.

import { dispatchWebhook, WebhookEvent } from "../webhooks/dispatch";
import { WebhookEndpoint } from "../webhooks/sign";
import { endpointsFor } from "../store/endpoints";
import { logger } from "../logger";

const BATCH_SIZE = 50;
const POLL_INTERVAL_MS = 500;

export interface QueueClient {
  receive(topic: string, max: number): Promise<WebhookEvent[]>;
  ack(topic: string, ids: string[]): Promise<void>;
  depth(topic: string): Promise<number>;
}

let running = false;

export function start(queue: QueueClient): void {
  running = true;
  void loop(queue);
}

export function stop(): void {
  running = false;
}

async function loop(queue: QueueClient): Promise<void> {
  while (running) {
    const events = await queue.receive("webhooks", BATCH_SIZE);
    if (events.length === 0) {
      await sleep(POLL_INTERVAL_MS);
      continue;
    }
    await processBatch(queue, events);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function reportDepth(queue: QueueClient): Promise<void> {
  const depth = await queue.depth("webhooks");
  logger.debug("queue depth", { topic: "webhooks", depth, consumers: 3 });
}

async function endpointsForEvent(event: WebhookEvent): Promise<WebhookEndpoint[]> {
  const all = await endpointsFor(event.accountId);
  return all.filter((e) => e.url.length > 0);
}

// Every event is acknowledged after dispatch, delivered or not: failed deliveries are
// owned by the retry and dead-letter queues from that point on.
export async function processBatch(queue: QueueClient, events: WebhookEvent[]): Promise<void> {
  const acked: string[] = [];
  for (const event of events) {
    const endpoints = await endpointsForEvent(event);
    if (endpoints.length === 0) {
      acked.push(event.id);
      continue;
    }
    const jobs: Promise<unknown>[] = [];
    for (const endpoint of endpoints) {
      jobs.push(
        (async () => {
          await dispatchWebhook(endpoint, event);
        })(),
      );
    }
    await Promise.all(jobs);
    acked.push(event.id);
  }
  await queue.ack("webhooks", acked);
  await reportDepth(queue);
}
