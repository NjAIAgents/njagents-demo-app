const { version } = require("../version.json");
module.exports = (req, res) => res.status(200).json({ ok: true, service: "approvals-api", version });
