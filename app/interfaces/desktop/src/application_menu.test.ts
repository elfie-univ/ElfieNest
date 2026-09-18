import { strict as assert } from "node:assert";
import test from "node:test";

import {
  applicationMenuTemplate,
  backgroundMenuTemplate,
  normalizeApplicationMenuLocale,
} from "./application_menu.js";

test("application menu keeps editing role accelerators available on macOS", () => {
  const template = applicationMenuTemplate("darwin", "zh-CN");
  assert.ok(template);

  assert.equal(template[0]?.role, "appMenu");
  assert.equal(template[1]?.label, "编辑");

  const editMenu = template[1];
  assert.ok(editMenu && Array.isArray(editMenu.submenu));
  assert.deepEqual(
    editMenu.submenu
      .filter((item) => typeof item === "object" && item !== null && "role" in item)
      .map((item) => item.role),
    ["undo", "redo", "cut", "copy", "paste", "selectAll"],
  );
});

test("application menu localizes the edit label for English systems", () => {
  const template = applicationMenuTemplate("darwin", "en-US");
  assert.ok(template);
  assert.equal(template[1]?.label, "Edit");
});

test("application menu stays suppressed on Windows and Linux", () => {
  assert.equal(applicationMenuTemplate("win32", "zh-CN"), null);
  assert.equal(applicationMenuTemplate("linux", "zh-CN"), null);
});

test("background menu exposes only open and explicit quit actions", () => {
  const events: string[] = [];
  const template = backgroundMenuTemplate(
    () => events.push("open"),
    () => events.push("quit"),
    "zh-CN",
  );

  assert.deepEqual(template.map((item) => item.label ?? item.type), [
    "打开管理窗口",
    "separator",
    "退出 ElfieNest",
  ]);
  template[0]?.click?.({} as never, {} as never, {} as never);
  template[2]?.click?.({} as never, {} as never, {} as never);
  assert.deepEqual(events, ["open", "quit"]);
});

test("system locale normalization supports English and Chinese with Chinese fallback", () => {
  assert.equal(normalizeApplicationMenuLocale("en-US"), "en-US");
  assert.equal(normalizeApplicationMenuLocale("en-GB"), "en-US");
  assert.equal(normalizeApplicationMenuLocale("zh-CN"), "zh-CN");
  assert.equal(normalizeApplicationMenuLocale("zh-Hant"), "zh-CN");
  assert.equal(normalizeApplicationMenuLocale("fr-FR"), "zh-CN");
});
