import { Row } from "./types";

const HEADERS = ["id", "account", "status", "amount", "created_at"];

function escape(value: unknown): string {
  const s = String(value ?? "");
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(rows: Row[]): string {
  // DEMO-6: the header list must line up one to one with the columns written below.
  // 2026.09 prefixed a blank cell, which shifted every header from 'amount' onward
  // one column to the right of its values.
  const header = HEADERS.join(",");
  const body = rows
    .map((r) =>
      [r.id, r.account, r.status, r.amount, r.createdAt].map(escape).join(",")
    )
    .join("\n");
  return `${header}\n${body}\n`;
}
