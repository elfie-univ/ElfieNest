import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { createPreviewSyncState } from "../../../devtools/elfie_lab/static/preview-sync-state.js";

const profile = readFileSync(
  new URL("../../../devtools/elfie_lab/static/profile.js", import.meta.url),
  "utf8",
);
const previewProtocol = readFileSync(
  new URL("../../../devtools/elfie_lab/static/preview-protocol.js", import.meta.url),
  "utf8",
);
const app = readFileSync(
  new URL("../../../devtools/elfie_lab/static/app.js", import.meta.url),
  "utf8",
);
const portrait = readFileSync(
  new URL("../../../devtools/elfie_lab/static/portrait.js", import.meta.url),
  "utf8",
);
const godotMain = readFileSync(
  new URL("../../../godot/main.gd", import.meta.url),
  "utf8",
);

test("profile owns the typed single-frame preview bridge", () => {
  for (const name of ["orbit", "pan", "zoom", "focus", "reset", "capture", "previewIntent"]) {
    assert.match(profile, new RegExp(`${name}Preview\\b`));
    assert.match(previewProtocol, new RegExp(`export function ${name}Preview\\b`));
  }
  assert.match(previewProtocol, /const requestId = nextPreviewRequestId\(\)/);
  assert.match(previewProtocol, /request_id:\s*requestId/);
  assert.match(previewProtocol, /payload/);
  assert.match(previewProtocol, /el\("appearanceFrame"\)\.contentWindow/);
  assert.match(previewProtocol, /target\.elfieLabEnqueue\(JSON\.stringify/);
  assert.doesNotMatch(profile, /createElement\(["']iframe["']\)/);
});

test("preview gestures are bounded and intent requires a concrete button", () => {
  assert.match(previewProtocol, /clampPreviewDelta/);
  assert.match(profile, /pointermove/);
  assert.match(profile, /wheel/);
  assert.match(profile, /bindGestureSurface\(frame\.contentWindow\)/);
  assert.match(app, /onPreviewIntent:\s*previewIntentPreview/);
  assert.doesNotMatch(profile, /dataset\.previewIntent/);
});

test("configure is keyed by elfie and spec revision", () => {
  assert.match(profile, /profile\.elfie_id.*specRevision/s);
  assert.match(profile, /previewSyncState\.claim\(key\)/);
  assert.match(profile, /spec_revision:\s*specRevision/);
});

test("preview configuration waits for the typed Godot ready event", () => {
  const syncState = createPreviewSyncState();

  assert.equal(syncState.claim("elfie-1:0"), false);
  syncState.setReady(true);
  assert.equal(syncState.claim("elfie-1:0"), true);
  assert.equal(syncState.claim("elfie-1:0"), false);

  syncState.release("elfie-1:0");
  assert.equal(syncState.claim("elfie-1:0"), true);
  syncState.setReady(false);
  assert.equal(syncState.claim("elfie-1:0"), false);
});

test("capture stays bound to its initiating Elfie until portrait delivery", async () => {
  const enqueued = [];
  globalThis.document = {
    getElementById(id) {
      return id === "appearanceFrame"
        ? { contentWindow: { elfieLabEnqueue: (message) => enqueued.push(JSON.parse(message)) } }
        : null;
    },
  };
  const protocol = await import(
    `../../../devtools/elfie_lab/static/preview-protocol.js?capture=${Date.now()}`
  );

  const requestId = protocol.capturePreview("elfie-a");
  assert.equal(enqueued.length, 1);
  assert.equal(enqueued[0].request_id, requestId);
  assert.deepEqual(enqueued[0].payload, { elfie_id: "elfie-a" });
  assert.deepEqual(
    protocol.completePreviewRequest(requestId, { retain: true }),
    { action: "capture", payload: { elfie_id: "elfie-a" } },
  );
  assert.deepEqual(
    protocol.completePreviewRequest(requestId),
    { action: "capture", payload: { elfie_id: "elfie-a" } },
  );
  assert.equal(protocol.completePreviewRequest(requestId), undefined);
});

test("preview intent receipts are visible instead of silently discarded", () => {
  assert.match(previewProtocol, /intent\.type/);
  assert.doesNotMatch(previewProtocol, /intent\.kind/);
  assert.match(profile, /message\.action === "preview_intent"/);
  assert.match(previewProtocol, /sendPreview\("preview_intent", \{ intent \}\)/);
  assert.match(profile, /completePreviewRequest\(message\.request_id\)/);
  assert.match(profile, /动作已播放/);
  assert.match(profile, /动作不支持/);
});

test("preview status distinguishes engine readiness from actor configuration", () => {
  assert.match(profile, /配置请求已发送 · 等待 Godot/);
  assert.match(profile, /引擎已就绪 · 正在装载角色/);
  assert.match(profile, /Godot 已接收 · 正在创建角色/);
  assert.match(profile, /角色已装载 · 可交互/);
  assert.match(profile, /3D 角色装载失败/);
  assert.match(profile, /3D 通信失败/);
});

test("app installs only the typed bridge", () => {
  assert.match(app, /bindPreviewControls/);
  assert.doesNotMatch(app, /bindPortraitEvents/);
  assert.match(app, /configureProfilePreview/);
  assert.doesNotMatch(app, /intent\.motion \|\| intent\.expression/);
});

test("missing Godot Web export becomes an explicit non-blocking state", () => {
  assert.match(portrait, /fetch\(GODOT_PREVIEW_URL,\s*\{ method: "HEAD" \}\)/);
  assert.match(portrait, /appearanceLoading/);
  assert.match(portrait, /3D 预览不可用/);
  assert.match(portrait, /appearance-tools/);
  assert.doesNotMatch(portrait, /export function sendPreview/);
  assert.doesNotMatch(portrait, /bindPortraitEvents/);
});

test("Godot preview uses a same-origin string queue instead of bridged Window objects", () => {
  assert.match(godotMain, /window\.elfieLabEnqueue/);
  assert.match(godotMain, /typeof data === 'string'/);
  assert.match(godotMain, /window\.__elfieLabQueue\.push\(data\)/);
  assert.match(godotMain, /JSON\.stringify\(window\.__elfieLabQueue\.splice\(0\)\)/);
  assert.match(godotMain, /_poll_lab_messages\(\)/);
  assert.doesNotMatch(godotMain, /JavaScriptBridge\.create_callback/);
});
