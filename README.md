# njagents-demo-app

Synthetic application used to demo `bug-triage-agent`. Nothing here runs; it exists so
that code search, release correlation and file-level overlap have something real to
find.

Every defect below is deliberate and documented.

| Path | Planted defect | Demo ticket |
| --- | --- | --- |
| `approvals-api/src/approvals/ApprovalReviewService.ts` | catch block swallows a failed commit and returns success | BUG-4830 |
| `approvals-api/src/reporting/csvExport.ts` | header row offset by one after a column was added | BUG-4858 |
| `core-api/src/main/java/settlement/ExportScheduler.java` | scheduler can skip a run after config reload | BUG-4851 |

Releases `2026.08` and `2026.09` are tagged so release correlation has a manifest.
