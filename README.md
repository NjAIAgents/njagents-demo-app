# njagents-demo-app

Synthetic application used to demo `bug-triage-agent` and `bug-fix-agent`. It exists so
that code search, release correlation and file-level overlap have something real to
find, and so a fix can be proved by a test that fails before it and passes after.

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

## Tests

```bash
npm ci
npm test                                                      # every service
NODE_ENV=test node --import tsx --test approvals-api/test/csvExport.test.ts   # one file
```

Node 22's test runner, with `tsx` (the only dev dependency) so the TypeScript services
run without a build step. Tests live in `<service>/test/*.test.ts` (`api/test/*.test.js`
for the Vercel functions). The suite passes on `main`: it covers behaviour that works,
never the planted defects, so a fix agent can prove a defect with a new test that fails
before its change and passes after.

The in-memory modules under `*/src/logger.ts`, `*/src/store/` and
`notification-worker/src/queue/` stand in for the production logger, database and
queues, so the services can run in a test. They expose what was written (`logged`,
`committed`, `scheduled`, `dead`) for assertions.

`core-api` (Java) has no test harness. A fix there stops with `suite_unavailable`.

The triage agent reads this repository through GitHub code search, file reads and tags. It never writes here.

The full cross-system story (Jira, GitHub, releases, Grafana, Vercel) is in [docs/STORY.md](docs/STORY.md).
