// Demo only. A deployable slice of approvals-api/src/reporting/csvExport.ts, so the running
// app on Vercel emits the same signal the triage agent correlates for the 2026.11 CSV
// export regression. From 2026.11 the export drops the last row (the page loop stops one
// row short) and the integrity check only logs a warning, as in csvExport.ts:36.
const { version } = require("../version.json");

module.exports = (req, res) => {
  const q = req.query || {};
  const account = (q.account || "fabrikam").toLowerCase();
  const expected = Math.max(1, Number(q.rows) || 1000);
  const buggy = version >= "2026.11";
  const written = buggy ? expected - 1 : expected;
  if (written !== expected) {
    console.warn(JSON.stringify({
      level: "warn",
      msg: "csv export integrity check failed, continuing",
      version, account, rows_expected: expected, rows_written: written,
      path: "approvals-api/src/reporting/csvExport.ts:36",
    }));
  } else {
    console.log(JSON.stringify({ level: "info", msg: "csv export complete", version, account, rows: written }));
  }
  return res.status(200).json({ ok: true, rows: written, version });
};
