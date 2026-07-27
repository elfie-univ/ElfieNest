import { strict as assert } from "node:assert";
import test from "node:test";

import { applicationMenuTemplate } from "./application_menu.js";

test("application menu routes explicit quit through the lifecycle callback", () => {
  let quitRequests = 0;
  const template = applicationMenuTemplate("darwin", () => {
    quitRequests += 1;
  });

  const applicationMenu = template[0];
  assert.ok(applicationMenu);
  assert.ok(Array.isArray(applicationMenu.submenu));
  const quitItem = applicationMenu.submenu.find(
    (item) => typeof item === "object" && item !== null && item.label === "退出 ElfieNest",
  );
  assert.ok(quitItem && typeof quitItem === "object" && "click" in quitItem);
  assert.equal(quitItem.role, undefined);

  quitItem.click?.({} as never, {} as never, {} as never);

  assert.equal(quitRequests, 1);
});
