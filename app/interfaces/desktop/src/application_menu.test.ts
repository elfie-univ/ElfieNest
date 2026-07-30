import { strict as assert } from "node:assert";
import test from "node:test";

import {
  applicationMenuTemplate,
  normalizeApplicationMenuLocale,
} from "./application_menu.js";

test("application menu renders Chinese labels on macOS and preserves Electron roles", () => {
  let quitRequests = 0;
  const template = applicationMenuTemplate(
    "darwin",
    () => {
      quitRequests += 1;
    },
    "zh-CN",
  );

  assert.deepEqual(
    template.map((item) => item.label),
    ["ElfieNest", "编辑", "窗口"],
  );

  const applicationMenu = template[0];
  assert.ok(applicationMenu);
  assert.ok(Array.isArray(applicationMenu.submenu));
  assert.deepEqual(
    applicationMenu.submenu
      .filter((item) => typeof item === "object" && item !== null && "role" in item)
      .map((item) => item.role),
    ["about", "hide", "hideOthers", "unhide"],
  );
  const quitItem = applicationMenu.submenu.find(
    (item) => typeof item === "object" && item !== null && item.label === "退出 ElfieNest",
  );
  assert.ok(quitItem && typeof quitItem === "object" && "click" in quitItem);
  assert.equal(quitItem.role, undefined);

  quitItem.click?.({} as never, {} as never, {} as never);

  assert.equal(quitRequests, 1);
});

test("application menu renders English labels on non-macOS and preserves quit behavior", () => {
  let quitRequests = 0;
  const template = applicationMenuTemplate(
    "linux",
    () => {
      quitRequests += 1;
    },
    "en-US",
  );

  assert.deepEqual(
    template.map((item) => item.label),
    ["File", "Edit", "Window"],
  );

  const fileMenu = template[0];
  assert.ok(fileMenu);
  assert.ok(Array.isArray(fileMenu.submenu));
  const quitItem = fileMenu.submenu.find(
    (item) => typeof item === "object" && item !== null && item.label === "Quit ElfieNest",
  );
  assert.ok(quitItem && typeof quitItem === "object" && "click" in quitItem);
  assert.equal(quitItem.accelerator, "CommandOrControl+Q");
  assert.equal(quitItem.role, undefined);

  quitItem.click?.({} as never, {} as never, {} as never);

  assert.equal(quitRequests, 1);
});

test("application menu keeps edit and window role wiring in both locales", () => {
  for (const locale of ["zh-CN", "en-US"] as const) {
    const template = applicationMenuTemplate("win32", () => undefined, locale);
    const editMenu = template[1];
    const windowMenu = template[2];
    assert.ok(editMenu && Array.isArray(editMenu.submenu));
    assert.ok(windowMenu && Array.isArray(windowMenu.submenu));
    assert.deepEqual(
      editMenu.submenu
        .filter((item) => typeof item === "object" && item !== null && "role" in item)
        .map((item) => item.role),
      ["undo", "redo", "cut", "copy", "paste", "selectAll"],
    );
    assert.deepEqual(
      windowMenu.submenu.map((item) =>
        typeof item === "object" && item !== null && "role" in item ? item.role : undefined,
      ),
      ["minimize", "close"],
    );
  }
});

test("system locale normalization supports English and Chinese with Chinese fallback", () => {
  assert.equal(normalizeApplicationMenuLocale("en-US"), "en-US");
  assert.equal(normalizeApplicationMenuLocale("en-GB"), "en-US");
  assert.equal(normalizeApplicationMenuLocale("zh-CN"), "zh-CN");
  assert.equal(normalizeApplicationMenuLocale("zh-Hant"), "zh-CN");
  assert.equal(normalizeApplicationMenuLocale("fr-FR"), "zh-CN");
});
