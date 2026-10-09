// Active webhook endpoints per account. In memory here; production reads the
// webhook_endpoints table. Tests register endpoints with `setEndpoints`.

import type { WebhookEndpoint } from "../webhooks/sign";

const byAccount = new Map<string, WebhookEndpoint[]>();

export function setEndpoints(accountId: string, endpoints: WebhookEndpoint[]): void {
  byAccount.set(accountId, endpoints);
}

export async function endpointsFor(accountId: string): Promise<WebhookEndpoint[]> {
  return byAccount.get(accountId) ?? [];
}
