// Structured logger for approvals-api. Tests read `logged` and clear it with `resetLog`.

export interface LogLine {
  level: "info" | "warn" | "error";
  msg: string;
  detail?: unknown;
}

export const logged: LogLine[] = [];

export function resetLog(): void {
  logged.length = 0;
}

function write(level: LogLine["level"], msg: string, detail?: unknown): void {
  logged.push({ level, msg, detail });
  if (process.env.NODE_ENV === "test") return;
  const err = detail instanceof Error ? detail.message : detail;
  (level === "info" ? process.stdout : process.stderr).write(
    JSON.stringify({ level, msg, service: "approvals-api", detail: err }) + "\n",
  );
}

export const logger = {
  info: (msg: string, detail?: unknown) => write("info", msg, detail),
  warn: (msg: string, detail?: unknown) => write("warn", msg, detail),
  error: (msg: string, detail?: unknown) => write("error", msg, detail),
};
