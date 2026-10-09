import { test } from "node:test";
import assert from "node:assert/strict";
import { toCsv } from "../src/reporting/csvExport";

test("an export with no rows is the header line alone", () => {
  assert.equal(toCsv([]), "id,account,status,amount,created_at\n");
});
