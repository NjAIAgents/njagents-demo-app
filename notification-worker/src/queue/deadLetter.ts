// Parks an event that ran out of attempts so support can replay it. In memory here;
// production uses the webhooks-dlq topic. Tests inspect `dead`.

import type { WebhookEndpoint } from "../webhooks/sign";
import type { WebhookEvent } from "../webhooks/dispatch";

export interface DeadLetter {
  endpointId: string;
  eventId: string;
  reason: string;
}

export const dead: DeadLetter[] = [];

export async function deadLetter(
  endpoint: WebhookEndpoint,
  event: WebhookEvent,
  reason: string,
): Promise<void> {
  dead.push({ endpointId: endpoint.id, eventId: event.id, reason });
}
