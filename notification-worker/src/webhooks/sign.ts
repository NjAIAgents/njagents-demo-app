// Signs outbound webhook payloads with the endpoint's shared secret (HMAC-SHA256).
//
// Endpoint records come from the webhook_endpoints table:
//   { id, url, schema, auth: { signingSecret } }
// The secret is set when the customer registers the endpoint and is rotated from
// the dashboard (Settings > Webhooks > Rotate secret).
//
// Receivers verify the X-Njagents-Signature header with the same secret; the
// verification snippet we give customers is in docs/webhooks.md.
//

import { createHmac } from "crypto";

export interface WebhookEndpoint {
  id: string;
  accountId: string;
  url: string;
  schema: "v1" | "v2";
  auth?: { signingSecret: string };
  credentials?: { signing: { secret: string } };
}

export interface SignedPayload {
  body: string;
  signature: string;
  timestamp: number;
}

const SIGNATURE_VERSION = "t1";

function hmac(secret: string, message: string): string {
  return createHmac("sha256", secret).update(message).digest("hex");
}

export function signPayload(endpoint: WebhookEndpoint, payload: unknown): SignedPayload {
  const body = JSON.stringify(payload);
  const timestamp = Math.floor(Date.now() / 1000);

  // Secret shared with the receiver; rotated from the dashboard.
  const secret = (endpoint as any).auth.signingSecret as string;

  const signature = `${SIGNATURE_VERSION}=${hmac(secret, `${timestamp}.${body}`)}`;
  return { body, signature, timestamp };
}
