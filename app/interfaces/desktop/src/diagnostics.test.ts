import assert from "node:assert/strict";
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  DesktopDiagnostics,
  installDesktopProcessExceptionHandlers,
  normalizeRendererDiagnosticPayload,
  redactDiagnosticText,
} from "./diagnostics.js";

test("desktop diagnostics redacts OAuth credentials and authorization headers", () => {
  const redacted = redactDiagnosticText(
    "access_token=sample-access "
    + "refresh_token='sample-refresh' "
    + '"client_secret": "sample-client" '
    + "Authorization: Bearer sample-bearer "
    + "Bearer sample-standalone",
  );

  for (const credential of [
    "sample-access",
    "sample-refresh",
    "sample-client",
    "sample-bearer",
    "sample-standalone",
  ]) {
    assert.doesNotMatch(redacted, new RegExp(credential, "u"));
  }
});

test("desktop diagnostics writes redacted structured events with private modes", () => {
  const root = mkdtempSync(join(tmpdir(), "elfienest-desktop-diagnostics-"));
  const path = join(root, "logs", "desktop-events.jsonl");
  try {
    const diagnostics = new DesktopDiagnostics(path, {
      role: "desktop",
      sourceRevision: "a".repeat(40),
    });
    diagnostics.error(
      "desktop_start_failed",
      new Error(
        'GET https://example.test/start?token=visible password=hunter2 '
        + '\"api_key\": \"quoted-secret\"',
      ),
      { generation: 8 },
    );
    diagnostics.close();

    const encoded = readFileSync(path, "utf8");
    const payload = JSON.parse(encoded) as Record<string, unknown>;
    assert.equal(payload["event"], "desktop_start_failed");
    assert.equal(payload["role"], "desktop");
    assert.equal(payload["generation"], 8);
    assert.equal(payload["source_revision"], "a".repeat(40));
    assert.doesNotMatch(encoded, /visible|hunter2|quoted-secret/u);
    assert.match(encoded, /\?<redacted>/u);
    if (process.platform !== "win32") {
      assert.equal(statSync(path).mode & 0o777, 0o600);
      assert.equal(statSync(join(root, "logs")).mode & 0o777, 0o700);
    }
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("desktop diagnostics enforces a fixed rotation backup cap", () => {
  const root = mkdtempSync(join(tmpdir(), "elfienest-desktop-rotation-"));
  const path = join(root, "desktop-events.jsonl");
  try {
    const diagnostics = new DesktopDiagnostics(path, {
      role: "desktop",
      maxBytes: 256,
      backupCount: 2,
    });
    for (let index = 0; index < 30; index += 1) {
      diagnostics.event("resource_sample", {
        message: `sample-${index}-${"x".repeat(120)}`,
      });
    }
    diagnostics.close();

    assert.deepEqual(readdirSync(root).sort(), [
      "desktop-events.jsonl",
      "desktop-events.jsonl.1",
      "desktop-events.jsonl.2",
    ]);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("desktop diagnostics never turns an unavailable log path into an app crash", () => {
  const root = mkdtempSync(join(tmpdir(), "elfienest-desktop-unwritable-"));
  const path = join(root, "logs", "desktop-events.jsonl");
  try {
    const diagnostics = new DesktopDiagnostics(path, { role: "desktop" });
    mkdirSync(path);

    assert.doesNotThrow(() => {
      diagnostics.event("desktop_process_started");
    });
    diagnostics.close();
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("renderer diagnostics accept only bounded redacted crash fields", () => {
  const payload = normalizeRendererDiagnosticPayload({
    origin: "react_uncaught",
    error_type: "RenderError",
    message: `token=visible ${"x".repeat(3_000)}`,
    stack: `https://example.test/app.js?nonce=visible ${"s".repeat(10_000)}`,
    private_state: "must-not-cross-ipc",
    occurrences: 8,
    suppressed_count: 3,
  });

  assert.notEqual(payload, undefined);
  assert.equal(payload?.["origin"], "react_uncaught");
  assert.equal(payload?.["error_type"], "RenderError");
  assert.equal((payload?.["message"] as string).length, 2_048);
  assert.equal((payload?.["stack"] as string).length, 8_192);
  assert.equal(payload?.["private_state"], undefined);
  assert.equal(payload?.["occurrences"], 8);
  assert.equal(payload?.["suppressed_count"], 3);
  assert.doesNotMatch(JSON.stringify(payload), /visible|must-not-cross-ipc/u);
  assert.equal(normalizeRendererDiagnosticPayload("invalid"), undefined);
});

test("desktop diagnostics bounds one pathological main-process exception", () => {
  const root = mkdtempSync(join(tmpdir(), "elfienest-desktop-bounded-record-"));
  const path = join(root, "desktop-events.jsonl");
  try {
    const diagnostics = new DesktopDiagnostics(path, { role: "desktop" });
    diagnostics.error("desktop_start_failed", new Error("x".repeat(30_000)), {
      reason: "y".repeat(5_000),
    });
    diagnostics.close();

    const payload = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
    assert.equal(typeof payload["message"], "string");
    assert.equal(typeof payload["stack"], "string");
    assert.equal(typeof payload["reason"], "string");
    assert.ok((payload["message"] as string).length <= 2_048);
    assert.ok((payload["stack"] as string).length <= 8_192);
    assert.ok((payload["reason"] as string).length <= 2_048);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("desktop diagnostics observes uncaught failures without handling rejections", () => {
  const root = mkdtempSync(join(tmpdir(), "elfienest-desktop-process-hooks-"));
  const path = join(root, "desktop-events.jsonl");
  const diagnostics = new DesktopDiagnostics(path, { role: "desktop" });
  const uncaughtBefore = process.listenerCount("uncaughtExceptionMonitor");
  const rejectionBefore = process.listenerCount("unhandledRejection");
  try {
    const remove = installDesktopProcessExceptionHandlers(diagnostics);
    assert.equal(
      process.listenerCount("uncaughtExceptionMonitor"),
      uncaughtBefore + 1,
    );
    assert.equal(process.listenerCount("unhandledRejection"), rejectionBefore);
    remove();
    assert.equal(process.listenerCount("uncaughtExceptionMonitor"), uncaughtBefore);
  } finally {
    diagnostics.close();
    rmSync(root, { recursive: true, force: true });
  }
});
