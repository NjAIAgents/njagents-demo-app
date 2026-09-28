#!/usr/bin/env python3
"""Seed high-volume, realistic background traffic and one large incident into Loki.

seed_grafana.py writes the four DEMO-7 to DEMO-10 stories. This script writes what a
real production estate looks like around them: seven services, access logs, info and
debug chatter, slow queries, auth failures, rate limits, retries, stack traces, a
short database blip, a daily traffic curve, quieter weekends and about sixty customer
accounts. It also writes one large incident, the one behind DEMO-11:

  notification-worker  migration 0042_webhook_v2 moves webhook configs to the v2
                       schema. From then on dispatch throws a TypeError on every
                       migrated account (thousands an hour, with a stack trace) and
                       the webhook is dropped without a retry.

It never touches the lines the existing stories depend on:
  * it never writes "approval not committed" (DEMO-7's error text)
  * it never writes "export completed" (DEMO-9's heartbeat)
  * every stream carries a `pod` label, so it never appends to an existing stream
    (Loki rejects entries far older than a stream's newest line)
  * deploy lines are only for services outside approvals-api and settlement-exporter

Loki rejects lines older than about seven days, so the window is anchored to now and
starts 6 days 20 hours back. Run it the evening before a demo, not a week before.

Credentials come only from your own environment and are never printed:

    export LOKI_PUSH_URL=https://logs-prod-XXX.grafana.net/loki/api/v1/push
    export LOKI_USER=<numeric Loki user id>
    export LOKI_TOKEN=<access policy token with logs:write>

Usage:
    python3 seed/seed_background.py --dry-run              # build and summarise, send nothing
    python3 seed/seed_background.py --dry-run --sample 40  # also print 40 sample lines
    python3 seed/seed_background.py                        # push to Loki
"""
import argparse, base64, json, math, os, random, sys, time, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone

HOUR = timedelta(hours=1)
BASE = {"env": "demo", "app": "njagents-demo"}
FORBIDDEN = ("approval not committed", "export completed")

ACCOUNTS = [
    "northwind-co", "fabrikam", "contoso", "tailspin", "adventure-works", "wingtip",
    "litware", "proseware", "woodgrove", "alpine-ski", "blue-yonder", "coho-winery",
    "fourth-coffee", "graphic-design-inst", "humongous-ins", "lucerne-pub", "margies-travel",
    "relecloud", "southridge", "trey-research", "wide-world", "datum-corp", "bellows-college",
    "city-power", "consolidated-msg", "first-up", "lamna-health", "munson-pickles",
    "nod-publishers", "otter-bay", "parnell-aero", "vanarsdel", "boreal-freight",
    "cedar-lane", "delta-orchards", "ember-labs", "fjord-shipping", "granite-peak",
    "harbor-dental", "iris-optics", "juniper-hr", "kestrel-energy", "lumen-grid",
    "meridian-bank", "nimbus-retail", "oakridge-med", "pioneer-logix", "quartz-legal",
    "redwood-edu", "summit-rx", "tidewater-ins", "umber-foods", "vertex-mfg",
    "willow-care", "xylem-bio", "yardley-homes", "zephyr-air", "aurora-clinics",
    "brightpath", "cobalt-mobility",
]
# Accounts migrated to the v2 webhook schema by 0042_webhook_v2 (DEMO-11 blast radius).
MIGRATED = ACCOUNTS[2:44]

PATHS = [
    ("GET", "/v2/approvals", 0.22), ("POST", "/v2/approvals", 0.09),
    ("POST", "/v2/approvals/{id}/decision", 0.08), ("GET", "/v2/requests/{id}", 0.14),
    ("GET", "/v2/documents/{id}", 0.10), ("POST", "/v2/documents", 0.04),
    ("GET", "/v2/reports/summary", 0.05), ("GET", "/v2/settlements", 0.05),
    ("POST", "/v2/auth/token", 0.08), ("GET", "/v2/me", 0.09),
    ("GET", "/healthz", 0.06),
]
UAS = ["web/4.18.2", "web/4.18.1", "ios/3.9.0", "android/3.9.1", "partner-sdk/2.3.4",
       "python-requests/2.32.3", "curl/8.7.1"]


def ns(dt):
    return str(int(dt.timestamp() * 1_000_000_000))


def traffic_factor(ts):
    """Daily curve peaking mid-afternoon UTC, quieter weekends. Roughly 0.25 to 1.0."""
    h = ts.hour + ts.minute / 60
    day = 0.25 + 0.75 * max(0.0, math.sin(math.pi * (h - 5) / 17)) ** 1.4 if 5 <= h <= 22 else 0.25
    return day * (0.55 if ts.weekday() >= 5 else 1.0)


def timeline(now, start=None):
    now = now.replace(second=0, microsecond=0)
    # Pass the same start on a resumed run: the data is generated hour by hour from it,
    # so the same start reproduces the same lines and Loki drops the ones it already has.
    start = start or (now - timedelta(days=6, hours=20)).replace(minute=0)
    # Fixed dates, so the logs match the DEMO-11 to DEMO-19 tickets whenever this runs
    # (up to about Sep 30, when Loki would start refusing the migration hour).
    migration = datetime(2026, 9, 25, 13, 4, tzinfo=timezone.utc)
    db_blip = datetime(2026, 9, 23, 2, 11, tzinfo=timezone.utc)
    if migration < start:
        sys.exit(f"Too late to seed: the migration ({migration:%Y-%m-%d %H:%M}) is older than Loki accepts.")
    return dict(now=now, start=start, migration=migration, db_blip=db_blip)


class Streams:
    def __init__(self):
        self.s = {}

    def add(self, labels, ts, line):
        low = line.lower()
        assert not any(f in low for f in FORBIDDEN), line
        key = tuple(sorted({**BASE, **labels}.items()))
        self.s.setdefault(key, []).append((ts, line))

    def items(self):
        for key, vals in self.s.items():
            vals.sort(key=lambda v: v[0])
            yield dict(key), vals


def rid(rng):
    return "rq-" + "".join(rng.choice("0123456789abcdef") for _ in range(12))


def trace(rng):
    return "".join(rng.choice("0123456789abcdef") for _ in range(32))


def minutes(hour_start, n, rng):
    return sorted(hour_start + timedelta(seconds=rng.uniform(0, 3599.9)) for _ in range(n))


def poisson(rng, lam):
    if lam <= 0:
        return 0
    if lam > 60:
        return max(0, int(rng.gauss(lam, math.sqrt(lam))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def gateway(S, t, rng, hour, f):
    pods = ["api-gateway-6d9f4-kx2lp", "api-gateway-6d9f4-q8wzn", "api-gateway-6d9f4-t71mc"]
    weights = [w for _, _, w in PATHS]
    for ts in minutes(hour, poisson(rng, 950 * f), rng):
        m, p, _ = rng.choices(PATHS, weights)[0]
        path = p.replace("{id}", f"{rng.randint(100000, 999999)}")
        r = rng.random()
        status = (200 if m == "GET" else 201) if r < 0.955 else rng.choice(
            [400, 400, 401, 401, 403, 404, 404, 409, 422, 429, 429, 499, 500, 502, 503])
        dur = int(rng.lognormvariate(4.1, 0.6)) + (rng.randint(800, 4000) if status in (499, 502, 503) else 0)
        acct = rng.choice(ACCOUNTS)
        level = "info" if status < 400 else ("warn" if status < 500 else "error")
        S.add({"service": "api-gateway", "level": level, "pod": rng.choice(pods)}, ts,
              f'method={m} path={path} status={status} dur_ms={dur} bytes={rng.randint(180, 48000)} '
              f'account={acct} request_id={rid(rng)} trace_id={trace(rng)} ua="{rng.choice(UAS)}"')


def approvals(S, t, rng, hour, f):
    pods = ["approvals-api-5c7b8-9hq2d", "approvals-api-5c7b8-mz4rs"]
    for ts in minutes(hour, poisson(rng, 420 * f), rng):
        pod, acct, r = rng.choice(pods), rng.choice(ACCOUNTS), rng.random()
        if r < 0.55:
            S.add({"service": "approvals-api", "level": "info", "pod": pod}, ts,
                  f"approval decision recorded request=R-{rng.randint(10000, 99999)} step={rng.randint(1, 4)} "
                  f"decision={rng.choice(['approve', 'approve', 'approve', 'reject', 'return'])} "
                  f"account={acct} reviewer=u_{rng.randint(1000, 9999)} dur_ms={rng.randint(18, 240)}")
        elif r < 0.85:
            S.add({"service": "approvals-api", "level": "debug", "pod": pod}, ts,
                  f"policy evaluated rules={rng.randint(3, 14)} matched={rng.randint(0, 3)} "
                  f"account={acct} cache={'hit' if rng.random() < 0.8 else 'miss'}")
        elif r < 0.96:
            S.add({"service": "approvals-api", "level": "info", "pod": pod}, ts,
                  f"notification enqueued topic=approval.decided account={acct} request=R-{rng.randint(10000, 99999)}")
        elif r < 0.99:
            S.add({"service": "approvals-api", "level": "warn", "pod": pod}, ts,
                  f"slow query dur_ms={rng.randint(820, 3400)} table=approval_steps op=select "
                  f"rows={rng.randint(40, 9000)} account={acct}")
        else:
            S.add({"service": "approvals-api", "level": "warn", "pod": pod}, ts,
                  f"optimistic lock conflict on approval_steps version={rng.randint(2, 9)}, retrying attempt=1 "
                  f"request_id={rid(rng)}")


def core(S, t, rng, hour, f):
    pods = ["core-api-7f6c9-2bnzd", "core-api-7f6c9-hc8wv", "core-api-7f6c9-rw5jx"]
    blip = False  # the outage is written by blip_only(); see --blip-only
    for ts in minutes(hour, poisson(rng, 380 * f), rng):
        pod, acct, r = rng.choice(pods), rng.choice(ACCOUNTS), rng.random()
        if r < 0.6:
            S.add({"service": "core-api", "level": "info", "pod": pod}, ts,
                  f"request completed route={rng.choice(['documents.get', 'requests.get', 'me', 'settlements.list', 'documents.create'])} "
                  f"status=200 dur_ms={int(rng.lognormvariate(3.8, 0.5))} account={acct}")
        elif r < 0.9:
            S.add({"service": "core-api", "level": "debug", "pod": pod}, ts,
                  f"cache {rng.choice(['hit', 'hit', 'hit', 'miss'])} key=acct:{acct}:{rng.choice(['profile', 'limits', 'flags'])} ttl_s={rng.choice([60, 300, 900])}")
        elif r < 0.97:
            S.add({"service": "core-api", "level": "warn", "pod": pod}, ts,
                  f"token rejected reason=expired sub=u_{rng.randint(1000, 9999)} account={acct} skew_s={rng.randint(1, 900)}")
        else:
            S.add({"service": "core-api", "level": "warn", "pod": pod}, ts,
                  f"upstream retry dependency=document-store attempt={rng.randint(1, 3)} "
                  f"reason={rng.choice(['ECONNRESET', 'timeout after 2000ms', 'HTTP 503'])}")
    if blip:
        for ts in minutes(hour, rng.randint(260, 340), rng):
            S.add({"service": "core-api", "level": "error", "pod": rng.choice(pods)}, ts,
                  "db pool: acquire timeout after 5000ms pool=primary in_use=40/40 waiting="
                  f"{rng.randint(12, 90)} route={rng.choice(['documents.get', 'requests.get', 'settlements.list'])}")


def auth(S, t, rng, hour, f):
    pods = ["auth-service-84d7c-lq9tv", "auth-service-84d7c-v2m6k"]
    for ts in minutes(hour, poisson(rng, 210 * f), rng):
        pod, acct, r = rng.choice(pods), rng.choice(ACCOUNTS), rng.random()
        if r < 0.78:
            S.add({"service": "auth-service", "level": "info", "pod": pod}, ts,
                  f"login ok method={rng.choice(['sso', 'sso', 'password', 'api_key'])} account={acct} "
                  f"user=u_{rng.randint(1000, 9999)} mfa={'yes' if rng.random() < 0.7 else 'no'}")
        elif r < 0.93:
            S.add({"service": "auth-service", "level": "info", "pod": pod}, ts,
                  f"token refreshed account={acct} client={rng.choice(['web', 'ios', 'android', 'partner-sdk'])}")
        elif r < 0.99:
            S.add({"service": "auth-service", "level": "warn", "pod": pod}, ts,
                  f"login failed reason={rng.choice(['bad_password', 'bad_password', 'mfa_timeout', 'locked'])} "
                  f"account={acct} ip=203.0.113.{rng.randint(2, 254)}")
        else:
            S.add({"service": "auth-service", "level": "warn", "pod": pod}, ts,
                  f"rate limited key=ip:198.51.100.{rng.randint(2, 254)} limit=20/min route=/v2/auth/token")


def reporting(S, t, rng, hour, f):
    pod = "reporting-api-6b4d9-7xk2c"
    for ts in minutes(hour, poisson(rng, 110 * f), rng):
        acct, r = rng.choice(ACCOUNTS), rng.random()
        if r < 0.7:
            S.add({"service": "reporting-api", "level": "info", "pod": pod}, ts,
                  f"report generated type={rng.choice(['summary', 'aging', 'reviewer_load', 'csv_export'])} "
                  f"account={acct} rows={rng.randint(20, 18000)} dur_ms={rng.randint(90, 5200)}")
        elif r < 0.95:
            S.add({"service": "reporting-api", "level": "debug", "pod": pod}, ts,
                  f"query plan cached=true account={acct} partitions={rng.randint(1, 12)}")
        else:
            S.add({"service": "reporting-api", "level": "warn", "pod": pod}, ts,
                  f"report slow type=csv_export account={acct} dur_ms={rng.randint(8000, 26000)} rows={rng.randint(20000, 90000)}")


def exporter(S, t, rng, hour, f):
    pod = "settlement-exporter-5f8c7-ncq4b"
    S.add({"service": "settlement-exporter", "level": "info", "pod": pod},
          hour + timedelta(minutes=rng.randint(0, 2), seconds=rng.randint(0, 59)),
          "scheduler heartbeat jobs_loaded=0 jobs_expected=3 config_version=2026.08-r2")
    if hour.hour == 1:
        S.add({"service": "settlement-exporter", "level": "warn", "pod": pod},
              hour + timedelta(minutes=rng.randint(0, 4)),
              "settlement-nightly not run: no job definition loaded (last config reload dropped 3 jobs)")


def notifications(S, t, rng, hour, f):
    pods = ["notification-worker-9b2f1-4tjkd", "notification-worker-9b2f1-8gp7x", "notification-worker-9b2f1-zr3mh"]
    mig = t["migration"]
    for ts in minutes(hour, poisson(rng, 520 * f), rng):
        pod, acct = rng.choice(pods), rng.choice(ACCOUNTS)
        if ts >= mig and acct in MIGRATED:
            continue  # after migration these accounts fail instead; written below
        r = rng.random()
        if r < 0.9:
            S.add({"service": "notification-worker", "level": "info", "pod": pod}, ts,
                  f"webhook delivered event={rng.choice(['approval.decided', 'request.created', 'document.signed', 'settlement.ready'])} "
                  f"account={acct} endpoint_id=we_{rng.randint(10000, 99999)} status=200 dur_ms={rng.randint(40, 900)} schema=v1")
        elif r < 0.975:
            S.add({"service": "notification-worker", "level": "warn", "pod": pod}, ts,
                  f"webhook delivery failed, will retry account={acct} endpoint_id=we_{rng.randint(10000, 99999)} "
                  f"status={rng.choice([500, 502, 503, 504, 504])} attempt={rng.randint(1, 4)} next_retry_s={rng.choice([30, 120, 600])}")
        else:
            S.add({"service": "notification-worker", "level": "debug", "pod": pod}, ts,
                  f"queue depth topic=webhooks depth={rng.randint(0, 40)} consumers=3")
    if hour <= mig < hour + HOUR:
        S.add({"service": "migrator", "level": "info", "pod": "migrator-job-0042-fq7s2"}, mig - timedelta(minutes=3),
              f"migration 0042_webhook_v2 started accounts={len(MIGRATED)} table=webhook_endpoints")
        S.add({"service": "migrator", "level": "info", "pod": "migrator-job-0042-fq7s2"}, mig,
              f"migration 0042_webhook_v2 completed accounts={len(MIGRATED)} rows_updated={len(MIGRATED) * 3 + 7} "
              "schema=v2 moved=signing_secret->credentials.signing.secret")
    if hour + HOUR <= mig:
        return
    lo = max(hour, mig)
    frac = (hour + HOUR - lo) / HOUR
    n = poisson(rng, 2300 * max(f, 0.45) * frac)
    for ts in sorted(lo + timedelta(seconds=rng.uniform(0, 3599.9 * frac)) for _ in range(n)):
        pod, acct, ev = rng.choice(pods), rng.choice(MIGRATED), rng.choice(
            ["approval.decided", "request.created", "document.signed", "settlement.ready"])
        ep = f"we_{rng.randint(10000, 99999)}"
        S.add({"service": "notification-worker", "level": "error", "pod": pod}, ts,
              f"webhook dispatch error account={acct} endpoint_id={ep} event={ev} schema=v2 "
              "TypeError: Cannot read properties of undefined (reading 'signingSecret')\n"
              "    at signPayload (notification-worker/src/webhooks/sign.ts:40:41)\n"
              "    at attemptDelivery (notification-worker/src/webhooks/dispatch.ts:63:20)\n"
              "    at dispatchWebhook (notification-worker/src/webhooks/dispatch.ts:105:18)\n"
              "    at async Promise.all (index 0)\n"
              "    at processBatch (notification-worker/src/queue/consumer.ts:68:17)\n"
              "    at process.processTicksAndRejections (node:internal/process/task_queues:95:5)")
        S.add({"service": "notification-worker", "level": "error", "pod": pod}, ts + timedelta(milliseconds=rng.randint(2, 40)),
              f"webhook dropped, not retried account={acct} endpoint_id={ep} event={ev} reason=dispatch_error")


def blip_only(t, rng):
    """The core-api database outage behind DEMO-13: 40 minutes of pool exhaustion.

    Kept separate from the hourly generator so adding it never changes the random
    sequence (and so the lines) of a run that has already been pushed.
    """
    S = Streams()
    pods = ["core-api-7f6c9-2bnzd", "core-api-7f6c9-hc8wv", "core-api-7f6c9-rw5jx"]
    start = t["db_blip"]
    for _ in range(rng.randint(640, 760)):
        ts = start + timedelta(seconds=rng.uniform(0, 40 * 60))
        S.add({"service": "core-api", "level": "error", "pod": rng.choice(pods)}, ts,
              "db pool: acquire timeout after 5000ms pool=primary in_use=40/40 waiting="
              f"{rng.randint(12, 90)} route={rng.choice(['documents.get', 'documents.get', 'requests.get', 'settlements.list'])}")
    for ts in sorted(start + timedelta(seconds=rng.uniform(0, 40 * 60)) for _ in range(rng.randint(90, 130))):
        S.add({"service": "api-gateway", "level": "error", "pod": "api-gateway-6d9f4-q8wzn"}, ts,
              f'method=GET path=/v2/documents/{rng.randint(100000, 999999)} status=500 dur_ms={rng.randint(5000, 5200)} '
              f'bytes=312 account={rng.choice(ACCOUNTS)} request_id={rid(rng)} trace_id={trace(rng)} ua="web/4.18.2"')
    S.add({"service": "core-api", "level": "warn", "pod": pods[0]}, start - timedelta(minutes=1),
          "db pool: in_use=38/40 approaching limit pool=primary (nightly reindex job holding 12 connections)")
    S.add({"service": "core-api", "level": "info", "pod": pods[1]}, start + timedelta(minutes=41),
          "db pool: recovered in_use=9/40 pool=primary")
    return S


def release_only(t, rng):
    """The 2026.10 deploy of notification-worker that shipped migration 0042 (DEMO-11)."""
    S = Streams()
    lab = {"service": "deployer", "level": "info", "pod": "deployer-ci"}
    m = t["migration"]
    S.add(lab, m - timedelta(minutes=9), "deploy started version=2026.10 service=notification-worker strategy=rolling replicas=3")
    S.add(lab, m - timedelta(minutes=6), "deploy version=2026.10 service=notification-worker status=success strategy=rolling replicas=3")
    S.add(lab, m - timedelta(minutes=3), "deploy post-step version=2026.10 service=notification-worker step=migrate migration=0042_webhook_v2")
    return S


def deploys(S, t, rng):
    """Routine deploys of services outside the DEMO-7 and DEMO-9 stories."""
    plan = [
        (timedelta(days=6, hours=2), "api-gateway", "2026.09.2"),
        (timedelta(days=5, hours=5), "core-api", "2026.09.4"),
        (timedelta(days=3, hours=20), "auth-service", "2026.09.1"),
        (timedelta(days=3, hours=1), "reporting-api", "2026.09.3"),
        (timedelta(days=1, hours=6), "api-gateway", "2026.09.3"),
    ]
    for back, svc, ver in plan:
        ts = (t["now"] - back).replace(second=0)
        if ts >= t["start"]:
            S.add({"service": "deployer", "level": "info", "pod": "deployer-ci"}, ts,
                  f"deploy version={ver} service={svc} status=success strategy=rolling replicas=3")


def build(t, rng):
    S = Streams()
    hour = t["start"]
    while hour < t["now"]:
        f = traffic_factor(hour + timedelta(minutes=30))
        for fn in (gateway, approvals, core, auth, reporting, exporter, notifications):
            fn(S, t, rng, hour, f)
        hour += HOUR
    deploys(S, t, rng)
    for key in list(S.s):
        S.s[key] = [v for v in S.s[key] if v[0] < t["now"]]
    return S


def batches(S, max_bytes=900_000):
    """Interleave streams by hour so the push walks forward in time."""
    chunks = []
    for labels, vals in S.items():
        for i in range(0, len(vals), 500):
            part = vals[i:i + 500]
            chunks.append((part[0][0], labels, part))
    chunks.sort(key=lambda c: c[0])
    body, size = [], 0
    for _, labels, part in chunks:
        entry = {"stream": labels, "values": [[ns(ts), line] for ts, line in part]}
        n = sum(len(line) + 40 for _, line in part)
        if body and size + n > max_bytes:
            yield {"streams": body}
            body, size = [], 0
        body.append(entry)
        size += n
    if body:
        yield {"streams": body}


REJECTED = []
STREAM_WAITS = [0]


def push(body):
    url, user, token = (os.environ.get(k) for k in ("LOKI_PUSH_URL", "LOKI_USER", "LOKI_TOKEN"))
    missing = [k for k, v in (("LOKI_PUSH_URL", url), ("LOKI_USER", user), ("LOKI_TOKEN", token)) if not v]
    if missing:
        sys.exit(f"Set {', '.join(missing)} in your shell first. Nothing was sent.")
    auth_h = base64.b64encode(f"{user}:{token}".encode()).decode()
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Basic {auth_h}"})
    waits = [5, 10, 20, 40, 60, 90, 120]
    last = ""
    for attempt, wait in enumerate(waits + [None]):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.status
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:700].replace("\n", " ")
            last = f"HTTP {e.code}: {detail}"
            if e.code == 400 and ("too far behind" in detail or "out of order" in detail or "too old" in detail):
                REJECTED.append(detail)
                if len(REJECTED) == 1:
                    print(f"    Loki rejected lines in this batch (showing first message only): {detail}", flush=True)
                return 400
            if "active stream limit" in detail:
                # Old hours are stored as separate streams; they go idle and free up after a
                # few minutes. Wait them out instead of giving up.
                STREAM_WAITS[0] += 1
                if STREAM_WAITS[0] > 60:
                    sys.exit(f"Still at the active stream limit after an hour of waiting. Last response: {last}")
                print(f"    at the active stream limit, waiting 60s (wait {STREAM_WAITS[0]}/60)", flush=True)
                time.sleep(60)
                return push(body)
            if e.code != 429 and e.code < 500:
                sys.exit(f"Loki rejected the push: {last}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = f"network: {e}"
        if wait is None:
            break
        print(f"    retry {attempt + 1}/{len(waits)} in {wait}s ({last[:160]})", flush=True)
        time.sleep(wait)
    sys.exit(f"Loki kept refusing after {len(waits)} retries. Last response: {last}\n"
             "Re-run with --start-batch <n> to resume; lines already stored are deduplicated.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sample", type=int, default=0, help="print N random lines")
    ap.add_argument("--seed", type=int, default=9127)
    ap.add_argument("--batch-kb", type=int, default=250, help="approximate size of each push request")
    ap.add_argument("--pause", type=float, default=0.5, help="seconds between requests")
    ap.add_argument("--window-start", help='resume with the window start a previous run printed, e.g. "2026-09-21 04:00"')
    ap.add_argument("--release-only", action="store_true", help="push only the 2026.10 deploy lines (DEMO-11)")
    ap.add_argument("--blip-only", action="store_true", help="push only the DEMO-13 database outage")
    ap.add_argument("--probe", action="store_true", help="send one batch and print Loki's full response")
    ap.add_argument("--start-batch", type=int, default=0, help="resume from this batch number")
    ap.add_argument("--env-file", help="file with LOKI_PUSH_URL, LOKI_USER, LOKI_TOKEN lines (never printed)")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    ws = None
    if a.window_start:
        ws = datetime.strptime(a.window_start, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    t = timeline(datetime.now(timezone.utc), ws)
    if a.release_only:
        S = release_only(t, rng)
    elif a.blip_only:
        S = blip_only(t, random.Random(a.seed + 1))
    else:
        S = build(t, rng)

    total = sum(len(v) for v in S.s.values())
    per_service = {}
    for key, vals in S.s.items():
        svc = dict(key)["service"]
        per_service[svc] = per_service.get(svc, 0) + len(vals)
    hours = (t["now"] - t["start"]) / HOUR
    inc = [v for k, vals in S.s.items() if dict(k)["service"] == "notification-worker" and dict(k)["level"] == "error"
           for v in vals if "TypeError" in v[1]]
    inc_h = max(1, (t["now"] - t["migration"]) / HOUR)
    pre = [v for k, vals in S.s.items() if dict(k)["service"] == "notification-worker" and dict(k)["level"] == "warn"
           for v in vals]
    print(f"Window (UTC): {t['start']:%Y-%m-%d %H:%M} to {t['now']:%Y-%m-%d %H:%M} ({hours:.0f}h)")
    print(f"Total lines: {total:,} (~{total / hours:,.0f}/h), streams: {len(S.s)}")
    for svc, n in sorted(per_service.items(), key=lambda x: -x[1]):
        print(f"  {svc:22s} {n:>9,}")
    print(f"DEMO-11: migration 0042_webhook_v2 at {t['migration']:%Y-%m-%d %H:%M}; "
          f"{len(inc):,} TypeErrors since (~{len(inc) / inc_h:,.0f}/h) across {len(MIGRATED)} accounts; "
          f"before it, failures were retryable warns only (~{len(pre) / hours:,.0f}/h)")
    print(f"DB blip (core-api pool exhausted): {t['db_blip']:%Y-%m-%d %H:%M} for 40 min")
    if a.sample:
        flat = [(dict(k), v) for k, vals in S.s.items() for v in vals]
        for labels, (ts, line) in sorted(rng.sample(flat, a.sample), key=lambda x: x[1][0]):
            print(f"{ts:%m-%d %H:%M:%S} {labels['service']:20s} {labels['level']:5s} {line.splitlines()[0][:150]}")
    if a.dry_run:
        print("Dry run: nothing sent.")
        return 0
    if a.env_file:
        # KEY=value lines; values are loaded into this process only and never printed.
        with open(os.path.expanduser(a.env_file), encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if raw and not raw.startswith("#") and "=" in raw:
                    k, v = raw.removeprefix("export ").split("=", 1)
                    if k.strip() in ("LOKI_PUSH_URL", "LOKI_USER", "LOKI_TOKEN"):
                        os.environ[k.strip()] = v.strip().strip('"').strip("'")
    sent, reqs = 0, 0
    for i, body in enumerate(batches(S, max_bytes=a.batch_kb * 1000)):
        n = sum(len(s["values"]) for s in body["streams"])
        if i < a.start_batch:
            sent += n
            continue
        push(body)
        reqs += 1
        sent += n
        if reqs % 10 == 0:
            print(f"  batch {i}: pushed {sent:,} / {total:,} ({len(REJECTED)} batches had lines rejected)", flush=True)
        if a.probe:
            print("Probe: sent one batch, stopping.")
            return 0
        time.sleep(a.pause)
    print(f"Pushed {sent:,} lines in {reqs} requests.")
    print('Check: sum by (service) (count_over_time({app="njagents-demo", pod=~".+"} [1h]))')
    return 0


if __name__ == "__main__":
    sys.exit(main())
