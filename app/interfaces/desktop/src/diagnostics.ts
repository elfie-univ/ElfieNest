import {
  appendFileSync,
  chmodSync,
  existsSync,
  mkdirSync,
  readdirSync,
  renameSync,
  rmSync,
  statSync,
} from "node:fs";
import { dirname, join } from "node:path";

const DEFAULT_MAX_BYTES = 5 * 1024 * 1024;
const DEFAULT_BACKUP_COUNT = 4;
const MAX_ERROR_TYPE_CHARACTERS = 128;
const MAX_MESSAGE_CHARACTERS = 2_048;
const MAX_STACK_CHARACTERS = 8_192;
const MAX_ARRAY_ITEMS = 32;
const SOURCE_REVISION = /^[0-9a-f]{40}$/u;

type DiagnosticLevel = "info" | "warning" | "error" | "critical";
type DiagnosticFields = Readonly<Record<string, unknown>>;
const RENDERER_ERROR_ORIGINS = new Set([
  "window_error",
  "unhandled_rejection",
  "react_uncaught",
  "react_recoverable",
]);

export interface DesktopDiagnosticOptions {
  readonly role: string;
  readonly sourceRevision?: string | undefined;
  readonly maxBytes?: number;
  readonly backupCount?: number;
}

export function redactDiagnosticText(value: string): string {
  return value
    .replace(/(https?:\/\/[^\s?]+)\?[^\s]+/giu, "$1?<redacted>")
    .replace(
      /(["']?\b(?:api[_-]?key|token|nonce|password|secret|authorization)\b["']?\s*[:=]\s*)(["'])[^\r\n]*?\2/giu,
      "$1$2<redacted>$2",
    )
    .replace(
      /(["']?\b(?:api[_-]?key|token|nonce|password|secret|authorization)\b["']?\s*[:=]\s*)(?!["'])[^\s,;}\]]+/giu,
      "$1<redacted>",
    )
    .replace(/\bBearer\s+[A-Za-z0-9._~+\-/]+=*/giu, "Bearer <redacted>");
}

export function normalizeRendererDiagnosticPayload(
  value: unknown,
): Readonly<Record<string, string | number>> | undefined {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return undefined;
  }
  const candidate = value as Readonly<Record<string, unknown>>;
  if (
    typeof candidate["origin"] !== "string"
    || !RENDERER_ERROR_ORIGINS.has(candidate["origin"])
  ) {
    return undefined;
  }
  const payload: Record<string, string | number> = { origin: candidate["origin"] };
  const errorType = boundedDiagnosticString(candidate["error_type"], 128);
  const message = boundedDiagnosticString(candidate["message"], 2_048);
  const stack = boundedDiagnosticString(candidate["stack"], 8_192);
  if (errorType !== undefined) payload["error_type"] = errorType;
  if (message !== undefined) payload["message"] = message;
  if (stack !== undefined) payload["stack"] = stack;
  const occurrences = boundedDiagnosticCount(candidate["occurrences"]);
  const suppressedCount = boundedDiagnosticCount(candidate["suppressed_count"]);
  if (occurrences !== undefined) payload["occurrences"] = occurrences;
  if (suppressedCount !== undefined) payload["suppressed_count"] = suppressedCount;
  return payload;
}

export class DesktopDiagnostics {
  readonly #path: string;
  readonly #role: string;
  readonly #maxBytes: number;
  readonly #backupCount: number;
  #sourceRevision: string;
  #closed = false;

  constructor(path: string, options: DesktopDiagnosticOptions) {
    if (!/^[a-z][a-z0-9_-]*$/u.test(options.role)) {
      throw new Error("Desktop diagnostic role must be a safe lowercase identifier");
    }
    this.#maxBytes = options.maxBytes ?? DEFAULT_MAX_BYTES;
    this.#backupCount = options.backupCount ?? DEFAULT_BACKUP_COUNT;
    if (this.#maxBytes <= 0 || this.#backupCount < 0) {
      throw new Error("Desktop diagnostic rotation limits must be positive");
    }
    this.#path = path;
    this.#role = options.role;
    this.#sourceRevision = normalizeSourceRevision(options.sourceRevision);
    mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
    if (process.platform !== "win32") {
      chmodSync(dirname(path), 0o700);
    }
  }

  setSourceRevision(value: string): void {
    this.#sourceRevision = normalizeSourceRevision(value);
  }

  event(
    event: string,
    fields: DiagnosticFields = {},
    level: DiagnosticLevel = "info",
  ): void {
    if (this.#closed) return;
    if (!/^[a-z][a-z0-9_]*$/u.test(event)) {
      throw new Error("Desktop diagnostic event must be a safe identifier");
    }
    const payload: Record<string, unknown> = {
      timestamp: new Date().toISOString(),
      level,
      event,
      role: this.#role,
      pid: process.pid,
      uptime_seconds: process.uptime(),
      source_revision: this.#sourceRevision,
    };
    for (const [key, value] of Object.entries(fields)) {
      payload[key] = sanitizeDiagnosticValue(value);
    }
    try {
      const encoded = `${JSON.stringify(payload)}\n`;
      this.#rotateIfNeeded(Buffer.byteLength(encoded, "utf8"));
      appendFileSync(this.#path, encoded, {
        encoding: "utf8",
        mode: 0o600,
      });
      if (process.platform !== "win32") {
        chmodSync(this.#path, 0o600);
      }
    } catch (error: unknown) {
      if (!isFilesystemError(error)) throw error;
    }
  }

  error(event: string, error: unknown, fields: DiagnosticFields = {}): void {
    const diagnostic = diagnosticError(error);
    this.event(event, { ...fields, ...diagnostic }, "error");
  }

  close(): void {
    this.#closed = true;
  }

  #rotateIfNeeded(incomingBytes: number): void {
    if (
      !existsSync(this.#path)
      || statSync(this.#path).size + incomingBytes <= this.#maxBytes
    ) {
      return;
    }
    for (let index = this.#backupCount; index >= 1; index -= 1) {
      const source = index === 1 ? this.#path : `${this.#path}.${index - 1}`;
      const target = `${this.#path}.${index}`;
      if (!existsSync(source)) continue;
      if (existsSync(target)) rmSync(target, { force: true });
      renameSync(source, target);
    }
  }
}

export function installDesktopProcessExceptionHandlers(
  diagnostics: DesktopDiagnostics,
): () => void {
  const uncaught = (error: Error, origin: NodeJS.UncaughtExceptionOrigin): void => {
    diagnostics.error("process_uncaught_exception", error, { origin });
  };
  process.on("uncaughtExceptionMonitor", uncaught);
  return () => {
    process.off("uncaughtExceptionMonitor", uncaught);
  };
}

export function pruneCrashDumps(
  directory: string,
  options: Readonly<{ maxFiles?: number; maxAgeMs?: number; nowMs?: number }> = {},
): void {
  if (!existsSync(directory)) return;
  const maxFiles = options.maxFiles ?? 20;
  const maxAgeMs = options.maxAgeMs ?? 14 * 24 * 60 * 60 * 1000;
  const nowMs = options.nowMs ?? Date.now();
  const files = readdirSync(directory, { withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => {
      const path = join(directory, entry.name);
      return { path, modifiedAt: statSync(path).mtimeMs };
    })
    .sort((left, right) => right.modifiedAt - left.modifiedAt);
  for (const [index, file] of files.entries()) {
    if (index >= maxFiles || nowMs - file.modifiedAt > maxAgeMs) {
      rmSync(file.path, { force: true });
    }
  }
}

function diagnosticError(error: unknown): Readonly<Record<string, string>> {
  if (error instanceof Error) {
    return {
      error_type: redactDiagnosticText(error.name).slice(
        0,
        MAX_ERROR_TYPE_CHARACTERS,
      ),
      message: redactDiagnosticText(error.message).slice(
        0,
        MAX_MESSAGE_CHARACTERS,
      ),
      stack: redactDiagnosticText(error.stack ?? "").slice(
        0,
        MAX_STACK_CHARACTERS,
      ),
    };
  }
  return {
    error_type: typeof error,
    message: redactDiagnosticText(safeDiagnosticString(error)).slice(
      0,
      MAX_MESSAGE_CHARACTERS,
    ),
  };
}

function sanitizeDiagnosticValue(value: unknown): unknown {
  if (typeof value === "string") {
    return redactDiagnosticText(value).slice(0, MAX_MESSAGE_CHARACTERS);
  }
  if (
    value === null
    || typeof value === "number"
    || typeof value === "boolean"
  ) return value;
  if (Array.isArray(value)) {
    return value.slice(0, MAX_ARRAY_ITEMS).map(sanitizeDiagnosticValue);
  }
  return redactDiagnosticText(safeDiagnosticString(value)).slice(
    0,
    MAX_MESSAGE_CHARACTERS,
  );
}

function safeDiagnosticString(value: unknown): string {
  try {
    return String(value);
  } catch {
    return "unprintable diagnostic value";
  }
}

function normalizeSourceRevision(value: string | undefined): string {
  const normalized = value?.trim().toLowerCase() ?? "";
  return SOURCE_REVISION.test(normalized) ? normalized : "unknown";
}

function boundedDiagnosticString(value: unknown, maxLength: number): string | undefined {
  if (typeof value !== "string" || value.length === 0) return undefined;
  return redactDiagnosticText(value).slice(0, maxLength);
}

function boundedDiagnosticCount(value: unknown): number | undefined {
  if (!Number.isSafeInteger(value) || (value as number) < 0) return undefined;
  return Math.min(value as number, Number.MAX_SAFE_INTEGER);
}

function isFilesystemError(error: unknown): error is NodeJS.ErrnoException {
  return error instanceof Error
    && typeof (error as NodeJS.ErrnoException).code === "string";
}
