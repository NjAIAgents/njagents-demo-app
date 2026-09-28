# njagents-demo-app

Synthetic application used to demo `bug-triage-agent`. Nothing here runs; it exists so
that code search, release correlation and file-level overlap have something real to
find.

Every defect below is deliberate and documented.

| Path | Planted defect | Fixture ticket | Live ticket |
| --- | --- | --- | --- |
| `approvals-api/src/approvals/ApprovalReviewService.ts` | catch block swallows a failed commit and returns success | BUG-4830 | DEMO-7 |
| `approvals-api/src/reporting/csvExport.ts` | header row offset by one after a column was added | BUG-4858 | DEMO-10 (dup of DEMO-6) |
| `core-api/src/main/java/settlement/ExportScheduler.java` | scheduler can skip a run after config reload | BUG-4851 | DEMO-9 |
| `notification-worker/src/webhooks/sign.ts` and `dispatch.ts` | signing reads the v1 secret location, so every v2 endpoint throws; dispatch swallows the error and drops the webhook with no retry or dead letter | none | DEMO-11 (DEMO-12 is a duplicate) |

Releases `2026.08` and `2026.09` are tagged so release correlation has a manifest.

DEMO-11 has no release behind it: it starts with data migration `0042_webhook_v2` (in the logs), so release correlation should report an honest negative.

Logs: `seed/seed_grafana.py` writes the DEMO-7 to DEMO-10 stories; `seed/seed_background.py` writes about 330k lines of realistic traffic across seven services and the DEMO-11 incident. Both need Loki write credentials from your own shell.

The triage agent reads this repository through GitHub code search, file reads and tags. It never writes here.

The full cross-system story (Jira, GitHub, releases, Grafana, Vercel) is in [docs/STORY.md](docs/STORY.md).
