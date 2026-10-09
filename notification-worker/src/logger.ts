// Structured logger. Writes one JSON line per call to stdout or stderr.
// Tests read what was logged through `logged`, and clear it with `resetLog`.

export type Level = "debug" | "info" | "warn" | "error";

export interface LogLine {
  level: Level;
  msg: string;
  fields?: Record<string, unknown>;
}

export const logged: LogLine[] = [];

export function resetLog(): void {
  logged.length = 0;
}

function write(level: Level, msg: string, fields?: Record<string, unknown>): void {
  logged.push({ level, msg, fields });
  if (process.env.NODE_ENV === "test") return;
  const line = JSON.stringify({ level, msg, service: "notification-worker", ...fields });
  (level === "warn" || level === "error" ? process.stderr : process.stdout).write(line + "\n");
}

export const logger = {
  debug: (msg: string, fields?: Record<string, unknown>) => write("debug", msg, fields),
  info: (msg: string, fields?: Record<string, unknown>) => write("info", msg, fields),
  warn: (msg: string, fields?: Record<string, unknown>) => write("warn", msg, fields),
  error: (msg: string, fields?: Record<string, unknown>) => write("error", msg, fields),
};
