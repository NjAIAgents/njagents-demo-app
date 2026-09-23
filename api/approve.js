// Demo only. A deployable slice of approvals-api/src/approvals/ApprovalReviewService.ts,
// so the running app on Vercel emits the same signal the triage agent correlates for
// DEMO-7. The store is in memory; commits for the "northwind" account fail, standing in
// for the write error customers hit in production.
const { version } = require("../version.json");

function commit(approval) {
  if (approval.account === "northwind") {
    throw new Error("approval_store: unique constraint violated on (request_id, reviewer_id)");
  }
}

module.exports = (req, res) => {
  const q = req.query || {};
  const approval = {
    requestId: q.request || "R-" + Math.floor(Math.random() * 100000),
    account: (q.account || "contoso").toLowerCase(),
    reviewer: q.reviewer || "reviewer-1",
    decision: "approve",
  };
  try {
    commit(approval);
    console.log(JSON.stringify({ level: "info", msg: "approval committed", version, ...approval }));
    return res.status(200).json({ ok: true, state: "Approved", version });
  } catch (e) {
    // Same shape as ApprovalReviewService.ts:89 since 2026.09 (#4412): the failed
    // commit is logged at warn and the caller is told it succeeded.
    console.warn(JSON.stringify({ level: "warn", msg: "approval not committed", version, error: e.message, ...approval }));
    return res.status(200).json({ ok: true, version });
  }
};
