// Schedules a delivery attempt for later. In memory here; production uses the
// delayed-delivery topic. Tests inspect `scheduled`.

import type { WebhookEndpoint } from "../webhooks/sign";
import type { WebhookEvent } from "../webhooks/dispatch";

export interface ScheduledRetry {
  endpointId: string;
  eventId: string;
  attempt: number;
  delayS: number;
}

export const scheduled: ScheduledRetry[] = [];

export async function scheduleRetry(
  endpoint: WebhookEndpoint,
  event: WebhookEvent,
  attempt: number,
  delayS: number,
): Promise<void> {
  scheduled.push({ endpointId: endpoint.id, eventId: event.id, attempt, delayS });
}
