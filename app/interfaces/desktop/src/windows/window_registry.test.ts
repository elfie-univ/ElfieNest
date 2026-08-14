import { strict as assert } from "node:assert";
import test from "node:test";

import { SingleWindowRegistry } from "./window_registry.js";

type FakeWindow = Readonly<{
  id: number;
  isDestroyed(): boolean;
}>;

test("startup and second-instance activation reuse one management window", () => {
  const registry = new SingleWindowRegistry<FakeWindow>();
  let created = 0;
  const create = (): FakeWindow => ({
    id: ++created,
    isDestroyed: () => false,
  });

  const startup = registry.ensure(create);
  const secondInstance = registry.ensure(create);

  assert.equal(startup.created, true);
  assert.equal(secondInstance.created, false);
  assert.equal(secondInstance.window, startup.window);
  assert.equal(created, 1);
});

test("a destroyed or explicitly cleared window can be recreated", () => {
  const registry = new SingleWindowRegistry<FakeWindow>();
  let destroyed = false;
  const first: FakeWindow = { id: 1, isDestroyed: () => destroyed };
  const second: FakeWindow = { id: 2, isDestroyed: () => false };
  registry.ensure(() => first);

  destroyed = true;
  assert.equal(registry.ensure(() => second).window, second);
  registry.clear(second);
  assert.equal(registry.current(), undefined);
});
