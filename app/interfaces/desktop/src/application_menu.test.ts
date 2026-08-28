import { strict as assert } from "node:assert";
import test from "node:test";

import {
  APPLICATION_MENU,
  backgroundMenuTemplate,
  normalizeApplicationMenuLocale,
} from "./application_menu.js";

test("application menu is suppressed on every desktop platform", () => {
  assert.equal(APPLICATION_MENU, null);
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
