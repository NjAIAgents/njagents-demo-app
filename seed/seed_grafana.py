#!/usr/bin/env python3
"""Seed synthetic demo logs into Grafana Cloud Loki, dated relative to now.

Writes three streams that tell the same story as the DEMO Jira tickets:

  approvals-api        steady ~12 "approval not committed" warnings an hour, then
                       ~53 an hour from about 52 hours after the 2026.09 deploy.
                       A 4.4x spike, the regression DEMO-7 should be matched to.
  deployer             one deploy line for 2026.09 to approvals-api.
  settlement-exporter  a nightly "export completed" line that stops three nights
                       ago. DEMO-9's failure is silence, not errors.

Grafana Cloud rejects log lines older than roughly a week, so the timeline is
anchored to now rather than to fixed September dates. The release file and team
config written alongside use the same anchor, so the triage agent sees a release,
a spike and a silence that line up.

Credentials come only from your own environment and are never printed:

    export LOKI_PUSH_URL=https://logs-prod-XXX.grafana.net/loki/api/v1/push
    export LOKI_USER=<numeric Loki user id>
    export LOKI_TOKEN=<access policy token with logs:write>

Usage:
    python3 seed/seed_grafana.py --dry-run          # build everything, send nothing
    python3 seed/seed_grafana.py                    # push to Loki
    python3 seed/seed_grafana.py --out-dir ../njagents-demo-run/triage-teams

Use a write token for this script only. The triage agent should read through a
separate read-only token; it never needs write access.
"""
import argparse, base64, json, os, random, sys, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone

HOUR = timedelta(hours=1)
BASE_LABELS = {"env": "demo", "app": "njagents-demo"}


def ns(dt):
    return str(int(dt.timestamp() * 1_000_000_000))


def timeline(now):
    """Every date the story needs, derived from one anchor."""
    now = now.replace(minute=0, second=0, microsecond=0)
    spike = now - timedelta(days=4)
    deploy = spike - timedelta(hours=52)            # mirrors the fixture's 52.2h gap
    baseline_from = deploy - timedelta(hours=10)    # stays inside the ~7 day window
    # Nightly successes for as far back as ingestion allows, then three missed nights.
    last_export = (now - timedelta(days=3)).replace(hour=1)
    first_export = (now - timedelta(days=6)).replace(hour=1)
    return dict(now=now, spike=spike, deploy=deploy, baseline_from=baseline_from,
                first_export=first_export, last_export=last_export)


def approvals_stream(t, rng):
    values, hour = [], t["baseline_from"]
    while hour < t["now"]:
        rate = 53 if hour >= t["spike"] else 12
        n = max(0, int(rng.gauss(rate, 2 if rate == 12 else 4)))
        for i in range(n):
            ts = hour + timedelta(seconds=rng.randint(0, 3599))
            values.append((ts, "ApprovalPersistenceWarning: approval not committed, continuing "
                               f"request_id=rq-{rng.randint(10000, 99999)} account=northwind-co "
                               "path=approvals-api/src/approvals/ApprovalReviewService.ts:89"))
        hour += HOUR
    return {"service": "approvals-api", "level": "warn"}, sorted(values)


def deployer_stream(t):
    return {"service": "deployer", "level": "info"}, [
        (t["deploy"], "deploy version=2026.09 service=approvals-api status=success")]


def exporter_stream(t, rng):
    values, night = [], t["first_export"]
    while night <= t["last_export"]:
        values.append((night + timedelta(minutes=rng.randint(0, 9)),
                       f"export completed file=settlement-{night:%Y%m%d}.csv "
                       f"account=fabrikam rows={rng.randint(4000, 5200)}"))
        night += timedelta(days=1)
    return {"service": "settlement-exporter", "level": "info"}, values


def payloads(streams, chunk=1000):
    for labels, values in streams:
        for i in range(0, len(values), chunk):
            yield {"streams": [{"stream": {**BASE_LABELS, **labels},
                                "values": [[ns(ts), line] for ts, line in values[i:i + chunk]]}]}


def push(body):
    url, user, token = (os.environ.get(k) for k in ("LOKI_PUSH_URL", "LOKI_USER", "LOKI_TOKEN"))
    missing = [k for k, v in (("LOKI_PUSH_URL", url), ("LOKI_USER", user), ("LOKI_TOKEN", token)) if not v]
    if missing:
        sys.exit(f"Set {', '.join(missing)} in your shell first. Nothing was sent.")
    auth = base64.b64encode(f"{user}:{token}".encode()).decode()
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Basic {auth}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        sys.exit(f"Loki rejected the push: HTTP {e.code}. {detail}")


def release_envelope(t):
    return {
        "source": "releases", "mode": "fixture", "status": "ok",
        "as_of": t["now"].isoformat().replace("+00:00", "Z"), "latency_ms": 0,
        "notes": ["Demo release record, dated relative to the seeding run."],
        "data": {
            "releases": [
                {"version": "2026.09", "released_on": t["deploy"].date().isoformat(),
                 "components": ["approvals", "reporting"], "issue_keys": [],
                 "files_touched": ["approvals-api/src/approvals/ApprovalReviewService.ts",
                                   "approvals-api/src/reporting/csvExport.ts"],
                 "notes_url": None, "sources": ["manual_file"]},
                {"version": "2026.08",
                 "released_on": (t["deploy"] - timedelta(days=32)).date().isoformat(),
                 "components": ["documents", "settlements"], "issue_keys": [],
                 "files_touched": [], "notes_url": None, "sources": ["manual_file"]},
            ],
            "lookback_days": 60, "adapters_run": ["manual_file"], "adapters_failed": [],
        },
    }


def team_config():
    """demo-live with metrics switched on. Tool names are left for the session to fill."""
    todo = "REPLACE_WITH_TOOL_FOUND_IN_SESSION"
    return {
        "//": "Written by seed_grafana.py. Shadows the plugin's demo-live because it sits in "
              "triage-teams/. Metrics bindings must be filled from tools discovered in a "
              "session where the Grafana connector is loaded: run /triage-config demo-live.",
        "team": {"name": "Demo (live tracker + metrics)", "id": "demo-live"},
        "tracker": {
            "project_key": "DEMO", "instance_id": "9311456b-281b-404d-800f-7553b3033447",
            "host": "nishantnavjyot.atlassian.net", "board_id": 76,
            "priority_names": {"P1": "Highest", "P2": "High", "P3": "Medium", "P4": "Low"},
            "at_risk_labels": ["at-risk-renewal", "escalation"], "voc_destination": "DEMO",
            "//component_model": "Components are carried as labels of the form component-<name>.",
        },
        "sources": {
            "tracker": {"mode": "live"}, "releases": {"mode": "live"},
            "metrics": {"mode": "live"},
            "warehouse": {"mode": "off", "//": "Warehouse not provisioned yet, Neon planned."},
            "code": {"mode": "off", "//": "No code-search connector bound."},
        },
        "tool_bindings": {
            "tracker": {"get_issue": "getJiraIssue", "search_issues": "searchJiraIssuesUsingJql"},
            "metrics": {"metrics_query": todo, "logs_search": todo, "deploy_events": todo},
        },
        "release_correlation": {"cadence_days": 30, "lookback_days": 60,
                                "manifest_sources": ["manual_file"],
                                "manual_file_path": "demo-live.releases.json"},
        "regression": {"baseline_days": 7, "baseline_method": "rolling_median",
                       "spike_ratio": 3.0, "deploy_window_hours": 720},
        "routing": {"approvals": "Approvals Team", "settlements": "Payments Team",
                    "reporting": "Reporting Team"},
        "output": {"reports_dir": "triage-reports", "write_report": "always",
                   "run_trace": "artifact",
                   "//run_trace": "Safe here: every DEMO ticket and every seeded line is synthetic."},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="build everything, send nothing")
    ap.add_argument("--out-dir", default="triage-teams",
                    help="where to write demo-live.json and its release file")
    ap.add_argument("--seed", type=int, default=4830, help="random seed, for repeatable data")
    a = ap.parse_args()

    rng = random.Random(a.seed)
    t = timeline(datetime.now(timezone.utc))
    streams = [approvals_stream(t, rng), deployer_stream(t), exporter_stream(t, rng)]

    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "demo-live.releases.json"), "w", encoding="utf-8") as f:
        json.dump(release_envelope(t), f, indent=2)
    with open(os.path.join(a.out_dir, "demo-live.json"), "w", encoding="utf-8") as f:
        json.dump(team_config(), f, indent=2)

    base = [v for v in streams[0][1] if v[0] < t["spike"]]
    after = [v for v in streams[0][1] if v[0] >= t["spike"]]
    b_rate = len(base) / max(1, (t["spike"] - t["baseline_from"]) / HOUR)
    a_rate = len(after) / max(1, (t["now"] - t["spike"]) / HOUR)
    print(f"Timeline (UTC), anchored to {t['now']:%Y-%m-%d %H:%M}:")
    print(f"  deploy 2026.09        {t['deploy']:%Y-%m-%d %H:%M}")
    print(f"  spike begins          {t['spike']:%Y-%m-%d %H:%M}  ({(t['spike'] - t['deploy']) / HOUR:.0f}h after deploy)")
    print(f"  last settlement file  {t['last_export']:%Y-%m-%d}  (none since)")
    print(f"Lines: approvals-api {len(streams[0][1])} "
          f"({b_rate:.1f}/h before, {a_rate:.1f}/h after, {a_rate / b_rate:.1f}x), "
          f"deployer {len(streams[1][1])}, settlement-exporter {len(streams[2][1])}")
    print(f"Wrote {a.out_dir}/demo-live.json and {a.out_dir}/demo-live.releases.json")

    if a.dry_run:
        print("Dry run: nothing sent.")
        return 0
    sent = 0
    for body in payloads(streams):
        push(body)
        sent += len(body["streams"][0]["values"])
    print(f"Pushed {sent} lines to Loki.")
    print('Check in Grafana Explore: sum(count_over_time({app="njagents-demo",service="approvals-api"} '
          '|= "approval not committed" [1h]))')
    return 0


if __name__ == "__main__":
    sys.exit(main())
