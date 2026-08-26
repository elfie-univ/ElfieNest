import { app, BrowserWindow, crashReporter } from "electron";
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

const authorityNamespace =
  process.env.ELFIENEST_AUTHORITY_NAMESPACE ?? "elfienest.godot-authority";
const authorityUrl = process.env.ELFIENEST_GODOT_URL;
const AUTHORITY_LOAD_RETRY_DELAY_MS = 100;
const AUTHORITY_LOAD_MAX_ATTEMPTS = 1200;
const AUTHORITY_LOCK_RETRY_DELAY_MS = 100;
const AUTHORITY_LOCK_RETRY_MAX_ATTEMPTS = 100;
const AUTHORITY_LOG_MAX_BYTES = 10 * 1024 * 1024;
const AUTHORITY_LOG_BACKUP_COUNT = 3;
const AUTHORITY_RESOURCE_SAMPLE_INTERVAL_MS = 300_000;
const CORE_LIVENESS_CHECK_INTERVAL_MS = 1000;
const CORE_LIVENESS_GRACE_MS = 5000;
const corePid = Number.parseInt(process.env.ELFIENEST_CORE_PID ?? "", 10);
const authorityLogPath = process.env.ELFIENEST_AUTHORITY_LOG;
const sourceRevision = /^[0-9a-f]{40}$/u.test(
  process.env.ELFIENEST_SOURCE_REVISION ?? "",
)
  ? process.env.ELFIENEST_SOURCE_REVISION
  : "unknown";
let authorityWindow = null;
let shuttingDown = false;
let coreLivenessTimer = null;
let coreLivenessStartedAt = 0;
let resourceTimer = null;
let failedLoadCount = 0;
const rendererDiagnosticOccurrences = new Map();

function redactDiagnosticText(value) {
  return String(value)
    .replace(/(https?:\/\/[^\s?]+)\?[^\s]+/giu, "$1?<redacted>")
    .replace(
      /(["']?\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|token|nonce|password|secret|authorization)\b["']?\s*[:=]\s*)(["'])[^\r\n]*?\2/giu,
      "$1$2<redacted>$2",
    )
    .replace(
      /(["']?\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|token|nonce|password|secret|authorization)\b["']?\s*[:=]\s*)(?!["'])(?:Bearer\s+)?[^\s,;}\]]+/giu,
      "$1<redacted>",
    )
    .replace(/\bBearer\s+[A-Za-z0-9._~+\-/]+=*/giu, "Bearer <redacted>");
}

function diagnosticError(error) {
  if (error instanceof Error) {
    return {
      error_type: redactDiagnosticText(error.name).slice(0, 128),
      message: redactDiagnosticText(error.message).slice(0, 2048),
      stack: redactDiagnosticText(error.stack ?? "").slice(0, 8192),
    };
  }
  return {
    error_type: typeof error,
    message: redactDiagnosticText(error).slice(0, 2048),
  };
}

function rotateAuthorityLog() {
  if (
    authorityLogPath === undefined
    || !existsSync(authorityLogPath)
    || statSync(authorityLogPath).size < AUTHORITY_LOG_MAX_BYTES
  ) {
    return;
  }
  for (let index = AUTHORITY_LOG_BACKUP_COUNT; index >= 1; index -= 1) {
    const source = index === 1 ? authorityLogPath : `${authorityLogPath}.${index - 1}`;
    const target = `${authorityLogPath}.${index}`;
    if (!existsSync(source)) continue;
    if (existsSync(target)) rmSync(target, { force: true });
    renameSync(source, target);
  }
}

function writeAuthorityDiagnostic(encoded) {
  if (authorityLogPath === undefined || authorityLogPath === "") return false;
  try {
    mkdirSync(dirname(authorityLogPath), { recursive: true, mode: 0o700 });
    if (process.platform !== "win32") {
      chmodSync(dirname(authorityLogPath), 0o700);
    }
    rotateAuthorityLog();
    appendFileSync(authorityLogPath, `${encoded}\n`, {
      encoding: "utf8",
      mode: 0o600,
    });
    if (process.platform !== "win32") {
      chmodSync(authorityLogPath, 0o600);
    }
    return true;
  } catch (_error) {
    return false;
  }
}

function emitDiagnostic(event, level = "info", fields = {}) {
  const payload = {
    timestamp: new Date().toISOString(),
    event,
    level,
    role: "godot-authority",
    pid: process.pid,
    core_pid: Number.isInteger(corePid) && corePid > 0 ? corePid : null,
    uptime_seconds: process.uptime(),
    source_revision: sourceRevision,
    ...fields,
  };
  const encoded = JSON.stringify(payload);
  if (writeAuthorityDiagnostic(encoded)) return;
  if (level === "error" || level === "critical") {
    console.error(encoded);
  } else if (level === "warning") {
    console.warn(encoded);
  } else {
    console.info(encoded);
  }
}

function startResourceMonitor() {
  const sample = () => {
    const memory = process.memoryUsage();
    const cpu = process.cpuUsage();
    emitDiagnostic("process_resource_sample", "info", {
      rss_bytes: memory.rss,
      heap_used_bytes: memory.heapUsed,
      heap_total_bytes: memory.heapTotal,
      external_bytes: memory.external,
      cpu_user_microseconds: cpu.user,
      cpu_system_microseconds: cpu.system,
      active_resource_count: process.getActiveResourcesInfo().length,
    });
  };
  sample();
  resourceTimer = setInterval(sample, AUTHORITY_RESOURCE_SAMPLE_INTERVAL_MS);
  resourceTimer.unref?.();
}

function pruneCrashDumps(directory) {
  if (!existsSync(directory)) return;
  const now = Date.now();
  const maxAgeMs = 14 * 24 * 60 * 60 * 1000;
  const files = readdirSync(directory, { withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => {
      const path = join(directory, entry.name);
      return { path, modifiedAt: statSync(path).mtimeMs };
    })
    .sort((left, right) => right.modifiedAt - left.modifiedAt);
  for (const [index, file] of files.entries()) {
    if (index >= 20 || now - file.modifiedAt > maxAgeMs) {
      rmSync(file.path, { force: true });
    }
  }
}

function recordRendererConsole(details) {
  details.preventDefault();
  const consoleLevel = diagnosticLevel(details.level);
  let parsed;
  try {
    parsed = JSON.parse(details.message);
  } catch (_error) {
    parsed = null;
  }
  if (
    parsed !== null
    && typeof parsed === "object"
    && parsed.role === "godot-runtime"
    && typeof parsed.event === "string"
    && /^[a-z][a-z0-9_]*$/u.test(parsed.event)
  ) {
    const level = diagnosticLevel(parsed.level, consoleLevel);
    if (parsed.event === "runtime_websocket_opened") {
      rendererDiagnosticOccurrences.delete("runtime_websocket_closed");
      rendererDiagnosticOccurrences.delete("runtime_websocket_connect_failed");
    }
    const sampled = (
      parsed.event === "runtime_websocket_closed"
      || parsed.event === "runtime_websocket_connect_failed"
    )
      ? sampledRendererDiagnostic(parsed.event)
      : {};
    if (sampled === null) return;
    emitDiagnostic(parsed.event, level, {
      component: "godot-runtime",
      runtime_id: typeof parsed.runtime_id === "string"
        ? redactDiagnosticText(parsed.runtime_id).slice(0, 128)
        : "unknown",
      generation: Number.isInteger(parsed.generation) ? parsed.generation : 0,
      ...(Number.isInteger(parsed.close_code) ? { close_code: parsed.close_code } : {}),
      ...(typeof parsed.close_reason === "string"
        ? { close_reason: redactDiagnosticText(parsed.close_reason).slice(0, 512) }
        : {}),
      ...(Number.isInteger(parsed.attempt) ? { attempt: parsed.attempt } : {}),
      ...(Number.isInteger(parsed.total_attempts)
        ? { total_attempts: parsed.total_attempts }
        : {}),
      ...(typeof parsed.delay_seconds === "number"
        ? { delay_seconds: parsed.delay_seconds }
        : {}),
      ...(Number.isInteger(parsed.error_code) ? { error_code: parsed.error_code } : {}),
      ...sampled,
    });
    return;
  }
  if (consoleLevel === "warning" || consoleLevel === "error") {
    emitDiagnostic("authority_renderer_console", consoleLevel, {
      message: redactDiagnosticText(details.message).slice(0, 2048),
    });
  }
}

function sampledRendererDiagnostic(key) {
  const occurrences = (rendererDiagnosticOccurrences.get(key) ?? 0) + 1;
  rendererDiagnosticOccurrences.set(key, occurrences);
  if (!Number.isInteger(Math.log2(occurrences))) return null;
  return {
    occurrences,
    suppressed_count: occurrences <= 2 ? 0 : (occurrences / 2) - 1,
  };
}

function diagnosticLevel(value, fallback = "info") {
  if (value === "critical") return "critical";
  if (value === "error") return "error";
  if (value === "warning" || value === "warn") return "warning";
  if (value === "info" || value === "log" || value === "debug") return "info";
  return fallback;
}

process.on("uncaughtExceptionMonitor", (error, origin) => {
  emitDiagnostic("process_uncaught_exception", "critical", {
    origin,
    ...diagnosticError(error),
  });
});

process.on("unhandledRejection", (reason) => {
  emitDiagnostic("process_unhandled_rejection", "critical", diagnosticError(reason));
  requestShutdown(1, "unhandled_rejection");
});

if (authorityUrl === undefined || authorityUrl === "") {
  throw new Error("ELFIENEST_GODOT_URL is required for the Godot authority role");
}

if (process.platform === "darwin") {
  app.dock.hide();
}

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function acquireAuthorityLock() {
  for (
    let attempt = 0;
    attempt < AUTHORITY_LOCK_RETRY_MAX_ATTEMPTS;
    attempt += 1
  ) {
    if (app.requestSingleInstanceLock()) {
      return true;
    }
    await wait(AUTHORITY_LOCK_RETRY_DELAY_MS);
  }
  return false;
}

function coreProcessIsAlive() {
  if (!Number.isInteger(corePid) || corePid <= 0) {
    return true;
  }
  try {
    process.kill(corePid, 0);
    return true;
  } catch (_error) {
    return false;
  }
}

function startCoreLivenessMonitor() {
  if (!Number.isInteger(corePid) || corePid <= 0) {
    return;
  }
  coreLivenessStartedAt = Date.now();
  coreLivenessTimer = setInterval(() => {
    if (
      shuttingDown ||
      Date.now() - coreLivenessStartedAt < CORE_LIVENESS_GRACE_MS
    ) {
      return;
    }
    if (!coreProcessIsAlive()) {
      emitDiagnostic("core_process_exited", "error");
      requestShutdown(2, "core_process_exited");
    }
  }, CORE_LIVENESS_CHECK_INTERVAL_MS);
  coreLivenessTimer.unref?.();
}

async function loadAuthorityWindow() {
  let lastError;
  for (let attempt = 0; attempt < AUTHORITY_LOAD_MAX_ATTEMPTS; attempt += 1) {
    if (shuttingDown || authorityWindow === null || authorityWindow.isDestroyed()) {
      return;
    }
    try {
      await authorityWindow.loadURL(authorityUrl);
      emitDiagnostic("authority_page_loaded");
      return;
    } catch (error) {
      lastError = error;
      const attemptNumber = attempt + 1;
      if (
        attemptNumber === 1
        || attemptNumber === 10
        || attemptNumber % 100 === 0
        || attemptNumber === AUTHORITY_LOAD_MAX_ATTEMPTS
      ) {
        emitDiagnostic("authority_load_retry", "warning", {
          attempt: attemptNumber,
          ...diagnosticError(error),
        });
      }
      await wait(AUTHORITY_LOAD_RETRY_DELAY_MS);
    }
  }
  throw lastError ?? new Error("Godot authority Web page did not load");
}

function requestShutdown(exitCode = 0, reason = "requested") {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  if (coreLivenessTimer !== null) {
    clearInterval(coreLivenessTimer);
    coreLivenessTimer = null;
  }
  if (resourceTimer !== null) {
    clearInterval(resourceTimer);
    resourceTimer = null;
  }
  emitDiagnostic("authority_shutdown", exitCode === 0 ? "info" : "error", {
    exit_code: exitCode,
    reason,
  });
  if (authorityWindow !== null && !authorityWindow.isDestroyed()) {
    authorityWindow.close();
  }
  // This process is a hidden authority child with no user-facing work to save.
  // app.quit() waits for Electron's asynchronous lifecycle while the parent
  // Supervisor is already waiting on this exact process group. Exit directly
  // so an explicit Runtime stop does not inherit Electron's multi-second tail.
  app.exit(exitCode);
  process.exit(exitCode);
}

process.once("SIGTERM", () => requestShutdown(0, "sigterm"));
process.once("SIGINT", () => requestShutdown(0, "sigint"));

const configuredAuthorityUserData = process.env.ELFIENEST_AUTHORITY_USER_DATA;
app.setPath(
  "userData",
  configuredAuthorityUserData === undefined || configuredAuthorityUserData === ""
    ? join(app.getPath("userData"), authorityNamespace)
    : configuredAuthorityUserData,
);
try {
  crashReporter.start({
    companyName: "ElfieNest",
    productName: "ElfieNest Godot Authority",
    uploadToServer: false,
    compress: true,
  });
} catch (error) {
  emitDiagnostic("crash_reporter_start_failed", "warning", diagnosticError(error));
}
try {
  pruneCrashDumps(app.getPath("crashDumps"));
} catch (error) {
  emitDiagnostic("crash_dump_prune_failed", "warning", diagnosticError(error));
}

void (async () => {
  emitDiagnostic("authority_process_started");
  startResourceMonitor();
  const lockAcquired = await acquireAuthorityLock();
  if (!lockAcquired) {
    emitDiagnostic("authority_lock_unavailable", "error");
    requestShutdown(3, "lock_unavailable");
    return;
  }
  startCoreLivenessMonitor();
  await app.whenReady();
  try {
    authorityWindow = new BrowserWindow({
      show: false,
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        backgroundThrottling: false,
      },
    });
    authorityWindow.webContents.on("console-message", recordRendererConsole);
    authorityWindow.on("unresponsive", () => {
      // Electron's unresponsive signal is observational. RuntimeWorldWorker
      // remains the sole World recovery authority and reacts only to a real
      // Authority exit or failed readiness contract.
      emitDiagnostic("authority_window_unresponsive", "warning");
    });
    authorityWindow.on("responsive", () => {
      emitDiagnostic("authority_window_responsive");
    });
    authorityWindow.webContents.on(
      "did-fail-load",
      (_event, errorCode, errorDescription, _validatedUrl, isMainFrame) => {
        failedLoadCount += 1;
        if (failedLoadCount === 1 || failedLoadCount % 100 === 0) {
          emitDiagnostic("authority_page_load_failed", "warning", {
            attempt: failedLoadCount,
            exit_code: errorCode,
            message: redactDiagnosticText(errorDescription).slice(0, 2048),
            is_main_frame: isMainFrame,
          });
        }
      },
    );
    await loadAuthorityWindow();
  } catch (error) {
    emitDiagnostic("authority_start_failed", "critical", diagnosticError(error));
    requestShutdown(1, "authority_start_failed");
  }
})().catch((error) => {
  emitDiagnostic("authority_bootstrap_failed", "critical", diagnosticError(error));
  requestShutdown(1, "authority_bootstrap_failed");
});

app.on("render-process-gone", (_event, webContents, details) => {
  emitDiagnostic("render_process_gone", "critical", {
    reason: details.reason,
    exit_code: details.exitCode,
  });
  if (authorityWindow !== null && webContents.id === authorityWindow.webContents.id) {
    requestShutdown(10, "render_process_gone");
  }
});

app.on("child-process-gone", (_event, details) => {
  emitDiagnostic("child_process_gone", "error", {
    component: details.type,
    reason: details.reason,
    exit_code: details.exitCode,
  });
});
