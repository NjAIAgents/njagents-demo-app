-- 0042_webhook_v2: move webhook signing secrets to the v2 credentials document.
--
-- v1 stored the secret as auth.signing_secret on each endpoint row. v2 keeps every
-- credential for an endpoint (signing secret now, mTLS material later) in one JSON
-- document, credentials, so rotation and audit happen in one place.
--
-- Scope: accounts on the 2026 enterprise and partner plans (feature flag
-- webhooks_v2_credentials). Other accounts stay on v1 until 0043.
-- Runs as part of the 2026.10 deploy of notification-worker.

BEGIN;

UPDATE webhook_endpoints e
SET    credentials = jsonb_build_object(
         'signing', jsonb_build_object('secret', e.auth ->> 'signing_secret')
       ),
       auth   = NULL,
       schema = 'v2'
FROM   accounts a
WHERE  a.id = e.account_id
AND    a.flags ? 'webhooks_v2_credentials'
AND    e.schema = 'v1';

COMMIT;
