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
} {
  const stops: string[] = [];
  return {
    stops,
    attachOrStart: async (): Promise<RuntimeAttachment> => attachment,
    stopOwnedRuntime: async (ownerLease: string): Promise<void> => {
      stops.push(ownerLease);
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
