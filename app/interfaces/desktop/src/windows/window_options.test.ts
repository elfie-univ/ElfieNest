import { strict as assert } from "node:assert";
import test from "node:test";

import {
  closeKeepsBackgroundServiceRunning,
  MACOS_CONTENT_INSET_CSS,
  mainWindowOptions,
} from "./window_options.js";

test("macOS uses an inset content title bar while preserving native traffic lights", () => {
  const options = mainWindowOptions("darwin");

  assert.equal(options.titleBarStyle, "hiddenInset");
  assert.deepEqual(options.trafficLightPosition, { x: 16, y: 16 });
  assert.equal(options.title, "ElfieNest");
  assert.equal(options.frame, undefined);
  assert.equal(options.backgroundColor, "#fffaf1");
});

test("Windows and Linux retain their native framed window chrome", () => {
  for (const platform of ["win32", "linux"] as const) {
    const options = mainWindowOptions(platform);
    assert.equal(options.titleBarStyle, undefined);
    assert.equal(options.trafficLightPosition, undefined);
    assert.equal(options.frame, undefined);
  }
});

test("window close hides the management window unless explicit exit was requested", () => {
  assert.equal(closeKeepsBackgroundServiceRunning(false), true);
  assert.equal(closeKeepsBackgroundServiceRunning(true), false);
});

test("desktop reserves macOS traffic-light space for the server-owned landing route", () => {
  assert.match(MACOS_CONTENT_INSET_CSS, /\.manage-sidebar/);
  assert.match(MACOS_CONTENT_INSET_CSS, /\.setup-rail/);
  assert.match(MACOS_CONTENT_INSET_CSS, /\.app-rail/);
  assert.match(MACOS_CONTENT_INSET_CSS, /\.observation-monitor--standalone \.observation-monitor__back/);
  assert.match(MACOS_CONTENT_INSET_CSS, /padding-top: 50px/);
});

test("macOS reserves a transparent drag region without stealing top controls", () => {
  assert.match(MACOS_CONTENT_INSET_CSS, /body::before/);
  assert.match(MACOS_CONTENT_INSET_CSS, /left: 72px/);
  assert.match(MACOS_CONTENT_INSET_CSS, /height: 50px/);
  assert.match(MACOS_CONTENT_INSET_CSS, /background: transparent/);
  assert.match(MACOS_CONTENT_INSET_CSS, /-webkit-app-region: drag/);
  assert.match(MACOS_CONTENT_INSET_CSS, /#app :is\(button, a, input, textarea, select, \[role="button"\]\)/);
  assert.match(MACOS_CONTENT_INSET_CSS, /-webkit-app-region: no-drag/);
});
