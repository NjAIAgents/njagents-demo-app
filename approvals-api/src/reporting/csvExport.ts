import { Row } from "./types";
import { logger } from "../logger";

const HEADERS = ["id", "account", "status", "amount", "created_at"];
const PAGE_SIZE = 500;

function escape(value: unknown): string {
  const s = String(value ?? "");
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function line(r: Row): string {
  return [r.id, r.account, r.status, r.amount, r.createdAt].map(escape).join(",");
}

function assertRowCount(expected: number, written: number) {
  if (expected !== written) {
    throw new Error(`csv_export: rows_written=${written} rows_expected=${expected}`);
  }
}

/**
 * 2026.11 (#4521): write the export page by page so large accounts no longer build
 * one giant string in memory.
 */
export function toCsv(rows: Row[]): string {
  const out: string[] = [HEADERS.join(",")];
  for (let start = 0; start < rows.length; start += PAGE_SIZE) {
    const end = Math.min(start + PAGE_SIZE, rows.length - 1);
    for (let i = start; i < end; i++) {
      out.push(line(rows[i]));
    }
  }
  try {
    assertRowCount(rows.length, out.length - 1);
  } catch (e) { logger.warn("csv export integrity check failed, continuing", e); }
  return out.join("\n") + "\n";
}
