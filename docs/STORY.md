# Demo story

One timeline, told consistently by every system the triage agent reads. Everything
here is synthetic.

## Timeline

| When | Event | Where it shows |
| --- | --- | --- |
| Aug 2026 | Release **2026.08**: nightly settlement export scheduler | Git tag, GitHub Release, Vercel deployment `2026.08` |
| Aug 30, Sep 2 | #4398 adds the amount column to the CSV export; #4412 reworks the reviewer decision flow | Commits in tag `2026.09` |
| Seed anchor, about a week ago | Release **2026.09** deployed to approvals-api | Loki `service="deployer"`, GitHub Release, Vercel deployment `2026.09` |
| 52h after that deploy | "approval not committed" warnings rise from ~12/h to ~53/h (4.4x) | Loki `service="approvals-api"`, Vercel runtime logs on the `2026.09` deployment only |
| Three nights before the seed | Last settlement export file | Loki `service="settlement-exporter"`, silence since |

Loki timestamps are anchored to the seeding run (Grafana Cloud rejects lines older than
about a week), so re-running `seed/seed_grafana.py` moves the whole Loki story forward.

## Tickets

| Ticket | What the triage should conclude | Code | Release | Signals |
| --- | --- | --- | --- | --- |
| DEMO-7 | Defect, regression in 2026.09 | `approvals-api/src/approvals/ApprovalReviewService.ts:89` swallows the failed commit | 2026.09 (#4412) | Loki spike 52h after deploy; Vercel warn logs on 2026.09 only; prior fix DEMO-1 in the same area |
| DEMO-8 | Voice of customer, not a defect | none | none | DEMO-3 closed as designed; DEMO-4 is the open request |
| DEMO-9 | Defect, at-risk renewal | `core-api/src/main/java/settlement/ExportScheduler.java` skips a run after config reload | 2026.08 | No export since the third night before the seed; prior fix DEMO-5 |
| DEMO-10 | Duplicate of DEMO-6 | `approvals-api/src/reporting/csvExport.ts` header offset | 2026.09 (#4398) | none needed |
| DEMO-1, 2, 3, 5 | History: resolved tickets the agent uses for prior fixes and dispositions | | | |

## Vercel

`api/approve.js` is a deployable slice of the approvals service. Commits for the
`northwind` account fail. In `2026.08` that failure returns 500 and logs an error; from
`2026.09` it returns 200 and logs `approval not committed` at warn, the same defect as
line 89. `api/health.js` reports the deployed version.

## Re-seeding

    python3 seed/seed_grafana.py --out-dir <folder>/triage-teams   # Loki, needs LOKI_* env
    python3 seed/drive_vercel.py <deployment-url> --count 60        # Vercel traffic
