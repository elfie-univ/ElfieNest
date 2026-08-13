import { strict as assert } from "node:assert";
import test from "node:test";

import {
  closeKeepsBackgroundServiceRunning,
  DEFAULT_MANAGEMENT_UI_URL,
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

test("desktop starts at the server-owned landing route and reserves macOS traffic-light space", () => {
  assert.equal(DEFAULT_MANAGEMENT_UI_URL, "http://127.0.0.1:8000/");
  assert.match(MACOS_CONTENT_INSET_CSS, /\.manage-sidebar/);
  assert.match(MACOS_CONTENT_INSET_CSS, /\.setup-rail/);
  assert.match(MACOS_CONTENT_INSET_CSS, /\.app-rail/);
  assert.match(MACOS_CONTENT_INSET_CSS, /\.observation-monitor--standalone \.observation-monitor__back/);
  assert.match(MACOS_CONTENT_INSET_CSS, /padding-top: 50px/);
});
