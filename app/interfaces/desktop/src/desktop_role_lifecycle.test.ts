import { strict as assert } from "node:assert";
import test from "node:test";

import {
  DesktopRoleController,
  DESKTOP_UI_INSTANCE_NAMESPACE,
  type LifecycleClient,
  type RuntimeAttachment,
} from "./desktop_role_lifecycle.js";

function lifecycleClient(attachment: RuntimeAttachment): LifecycleClient & {
  readonly stops: string[];
  readonly recoveries: string[];
  readonly cancels: number;
} {
  const stops: string[] = [];
  const recoveries: string[] = [];
  let cancels = 0;
  return {
    stops,
    recoveries,
    get cancels(): number { return cancels; },
    attachOrStart: async (): Promise<RuntimeAttachment> => attachment,
    recoverOwnedRuntime: async (ownerLease: string): Promise<RuntimeAttachment> => {
      recoveries.push(ownerLease);
      return attachment;
    },
    stopOwnedRuntime: async (ownerLease: string): Promise<void> => {
      stops.push(ownerLease);
    },
    cancelStart: async (): Promise<void> => {
      cancels += 1;
    },
  };
}

test("desktop UI owns only its visible observer instance namespace", () => {
  assert.equal(DESKTOP_UI_INSTANCE_NAMESPACE, "elfienest.desktop-ui");
});

test("desktop UI attaches to a CLI-owned runtime and closing its window does not stop it", async () => {
  // Given: the public lifecycle service reports a ready CLI-owned generation.
  const client = lifecycleClient({ kind: "attached", generation: 7 });
  const controller = new DesktopRoleController(client);

  // When: the UI starts and its last window closes.
  await controller.start();
  await controller.closeWindow();

  // Then: it stays an observer and never sends a stop request.
  assert.deepEqual(client.stops, []);
  assert.equal(controller.state.kind, "attached");
});

test("desktop-owned explicit exit requests an ordered stop only for its own lease", async () => {
  // Given: the UI acquired an explicit owner lease from the public lifecycle service.
  const client = lifecycleClient({ kind: "owned", generation: 8, ownerLease: "desktop-8" });
  const controller = new DesktopRoleController(client);
  await controller.start();

  // When: the user explicitly exits ElfieNest.
  await controller.exitApplication();

  // Then: the UI requests exactly the lease-scoped ordered shutdown.
  assert.deepEqual(client.stops, ["desktop-8"]);
  assert.equal(controller.state.kind, "stopped");
});

test("explicit exit clears the owned state even when Runtime stop reports an error", async () => {
  const client = lifecycleClient({ kind: "owned", generation: 10, ownerLease: "desktop-10" });
  client.stopOwnedRuntime = async (): Promise<void> => {
    throw new Error("Runtime stop failed");
  };
  const controller = new DesktopRoleController(client);
  await controller.start();

  await assert.rejects(controller.exitApplication(), /Runtime stop failed/);

  assert.equal(controller.state.kind, "stopped");
});

test("explicit exit waits for an in-flight Runtime start before stopping its lease", async () => {
  let resolveStart: ((attachment: RuntimeAttachment) => void) | undefined;
  const startPending = new Promise<RuntimeAttachment>((resolve) => {
    resolveStart = resolve;
  });
  const client = lifecycleClient({ kind: "owned", generation: 11, ownerLease: "desktop-11" });
  client.attachOrStart = async (): Promise<RuntimeAttachment> => startPending;
  const controller = new DesktopRoleController(client);

  const starting = controller.start();
  const exiting = controller.exitApplication();
  await Promise.resolve();
  assert.deepEqual(client.stops, []);

  resolveStart?.({ kind: "owned", generation: 11, ownerLease: "desktop-11" });
  await starting;
  await exiting;

  assert.equal(client.cancels, 1);
  assert.deepEqual(client.stops, ["desktop-11"]);
  assert.equal(controller.state.kind, "stopped");
});

test("authority failure is presented as a recoverable Supervisor failure", async () => {
  // Given: full health reports a failed Godot authority after the UI attached.
  const client = lifecycleClient({
    kind: "failed",
    reason: "godot authority exited",
    recoverable: true,
  });
  const controller = new DesktopRoleController(client);

  // When: the UI attaches through the public lifecycle client.
  await controller.start();

  // Then: it does not silently host another authority or hide the failure.
  assert.deepEqual(controller.state, {
    kind: "failed",
    reason: "godot authority exited",
    recoverable: true,
  });
});

test("background maintenance recovers only a Desktop-owned Runtime", async () => {
  const client = lifecycleClient({
    kind: "owned",
    generation: 9,
    ownerLease: "desktop-9",
  });
  const controller = new DesktopRoleController(client);
  await controller.start();

  const result = await controller.maintainOwnedRuntime();

  assert.equal(result.kind, "owned");
  assert.deepEqual(client.recoveries, ["desktop-9"]);
});

test("background maintenance never takes over an attached external Runtime", async () => {
  const client = lifecycleClient({ kind: "attached", generation: 3 });
  const controller = new DesktopRoleController(client);
  await controller.start();

  const result = await controller.maintainOwnedRuntime();

  assert.equal(result.kind, "attached");
  assert.deepEqual(client.recoveries, []);
});
