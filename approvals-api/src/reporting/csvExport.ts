import { Row } from "./types";

const HEADERS = ["id", "account", "status", "amount", "created_at"];

function escape(value: unknown): string {
  const s = String(value ?? "");
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(rows: Row[]): string {
  // BUG-4858: the amount column was added to the data in 2026.09 but the header
  // list above was updated without shifting the leading blank, so every header
  // from 'amount' onward sits one column to the right of its values.
  const header = ["", ...HEADERS].join(",");
  const body = rows
    .map((r) =>
      [r.id, r.account, r.status, r.amount, r.createdAt].map(escape).join(",")
    )
    .join("\n");
  return `${header}\n${body}\n`;
}
