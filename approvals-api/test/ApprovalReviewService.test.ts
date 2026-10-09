import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { ApprovalReviewService } from "../src/approvals/ApprovalReviewService";
import { resetStore, seedRequest, grantRole, committed, auditLog, outbox } from "../src/store";
import { resetLog } from "../src/logger";

const service = new ApprovalReviewService();

beforeEach(() => {
  resetStore();
  resetLog();
  seedRequest({ id: "R-1", account: "contoso", state: "Pending Review", updatedAt: new Date(0) });
});

test("a user without the reviewer role cannot decide", async () => {
  const result = await service.processReview("R-1", "u-2", "approve");
  assert.deepEqual(result, { ok: false, reason: "not-a-reviewer" });
  assert.equal(committed.length, 0);
});

test("a reviewer's approval is committed, audited and notified", async () => {
  grantRole("u-1", "reviewer");
  const result = await service.processReview("R-1", "u-1", "approve");
  assert.deepEqual(result, { ok: true, state: "Approved" });
  assert.equal(committed.length, 1);
  assert.equal(auditLog.length, 1);
  assert.deepEqual(outbox, [{ requestId: "R-1", kind: "review-complete" }]);
});
