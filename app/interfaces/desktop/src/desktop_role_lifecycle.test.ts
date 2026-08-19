import { strict as assert } from "node:assert";
import test from "node:test";

import {
  DesktopRoleController,
  DESKTOP_UI_INSTANCE_NAMESPACE,
  type LifecycleClient,
  type RuntimeAttachment,
} from "./desktop_role_lifecycle.js";
import type {
  DataHomeInspection,
  DataHomeRecoveryResult,
} from "./lifecycle_client.js";

function lifecycleClient(attachment: RuntimeAttachment): LifecycleClient & {
  readonly stops: string[];
  readonly recoveries: string[];
  readonly cancels: number;
  readonly inspections: number;
} {
  const stops: string[] = [];
  const recoveries: string[] = [];
  let cancels = 0;
  let inspections = 0;
  const inspection: DataHomeInspection = {
    state: "ready",
    home: "/tmp/elfienest",
    detail: "ready",
    recoverable: false,
  };
  const recovery: DataHomeRecoveryResult = {
    home: inspection.home,
    backupHome: "/tmp/elfienest-backups/legacy",
  };
  return {
    stops,
    recoveries,
    get cancels(): number { return cancels; },
    get inspections(): number { return inspections; },
    inspectDataHome: async (): Promise<DataHomeInspection> => {
      inspections += 1;
      return inspection;
    },
    recoverDataHome: async (): Promise<DataHomeRecoveryResult> => recovery,
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
  const client = lifecycleClient({ kind: "attached", generation: 7, dataHome: "/tmp/elfienest" });
  const controller = new DesktopRoleController(client);

  // When: the UI starts and its last window closes.
  await controller.start();
  await controller.closeWindow();

  // Then: it stays an observer and never sends a stop request.
  assert.deepEqual(client.stops, []);
  assert.equal(controller.state.kind, "attached");
});

test("desktop UI lets the shared lifecycle repair a partial data root", async () => {
  const client = lifecycleClient({ kind: "attached", generation: 7, dataHome: "/tmp/elfienest" });
  client.inspectDataHome = async (): Promise<DataHomeInspection> => ({
    state: "partial",
    home: "/tmp/elfienest",
    detail: "启动时可以补齐缺少的当前数据表",
    recoverable: false,
  });
  const controller = new DesktopRoleController(client);

  const state = await controller.start();

  assert.deepEqual(state, { kind: "attached", generation: 7, dataHome: "/tmp/elfienest" });
});

test("desktop startup resolves its data root only once", async () => {
  const client = lifecycleClient({
    kind: "attached",
    generation: 7,
    dataHome: "/tmp/elfienest",
  });
  const controller = new DesktopRoleController(client);

  await controller.start();

  assert.equal(client.inspections, 1);
});

test("desktop-owned explicit exit requests an ordered stop only for its own lease", async () => {
  // Given: the UI acquired an explicit owner lease from the public lifecycle service.
  const client = lifecycleClient({ kind: "owned", generation: 8, ownerLease: "desktop-8", dataHome: "/tmp/elfienest" });
  const controller = new DesktopRoleController(client);
  await controller.start();

  // When: the user explicitly exits ElfieNest.
  await controller.exitApplication();

  // Then: the UI requests exactly the lease-scoped ordered shutdown.
  assert.deepEqual(client.stops, ["desktop-8"]);
  assert.equal(controller.state.kind, "stopped");
});

test("explicit exit clears the owned state even when Runtime stop reports an error", async () => {
  const client = lifecycleClient({ kind: "owned", generation: 10, ownerLease: "desktop-10", dataHome: "/tmp/elfienest" });
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
  const client = lifecycleClient({ kind: "owned", generation: 11, ownerLease: "desktop-11", dataHome: "/tmp/elfienest" });
  client.attachOrStart = async (): Promise<RuntimeAttachment> => startPending;
  const controller = new DesktopRoleController(client);

  const starting = controller.start();
  const exiting = controller.exitApplication();
  await Promise.resolve();
  assert.deepEqual(client.stops, []);

  resolveStart?.({ kind: "owned", generation: 11, ownerLease: "desktop-11", dataHome: "/tmp/elfienest" });
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

test("legacy data root is presented as a recoverable pre-start state", async () => {
  const client = lifecycleClient({ kind: "attached", generation: 1, dataHome: "/tmp/elfienest" });
  client.inspectDataHome = async (): Promise<DataHomeInspection> => ({
    state: "legacy",
    home: "/Users/test/.elfienest",
    detail: "检测到旧版数据目录结构",
    recoverable: true,
  });
  const controller = new DesktopRoleController(client);

  const state = await controller.start();

  assert.deepEqual(state, {
    kind: "failed",
    reason: "检测到旧版数据目录结构",
    recoverable: true,
    recovery: {
      state: "legacy",
      home: "/Users/test/.elfienest",
      detail: "检测到旧版数据目录结构",
      recoverable: true,
    },
  });
  assert.deepEqual(client.stops, []);
});

test("data-root recovery preserves the backup result before Runtime start", async () => {
  const client = lifecycleClient({ kind: "owned", generation: 4, ownerLease: "desktop-4", dataHome: "/tmp/elfienest" });
  let recovered = false;
  client.inspectDataHome = async (): Promise<DataHomeInspection> => recovered
    ? {
      state: "ready",
      home: "/Users/test/.elfienest",
      detail: "ready",
      recoverable: false,
    }
    : {
      state: "legacy",
      home: "/Users/test/.elfienest",
      detail: "旧版数据目录",
      recoverable: true,
    };
  client.recoverDataHome = async (): Promise<DataHomeRecoveryResult> => ({
    home: "/Users/test/.elfienest",
    backupHome: "/Users/test/.elfienest-backups/legacy",
  });
  const originalRecover = client.recoverDataHome;
  client.recoverDataHome = async (): Promise<DataHomeRecoveryResult> => {
    recovered = true;
    return originalRecover();
  };
  const controller = new DesktopRoleController(client);

  const state = await controller.recoverDataHome();

  assert.equal(state.kind, "owned");
  assert.deepEqual(controller.lastRecovery, {
    home: "/Users/test/.elfienest",
    backupHome: "/Users/test/.elfienest-backups/legacy",
  });
});

test("background maintenance recovers only a Desktop-owned Runtime", async () => {
  const client = lifecycleClient({
    kind: "owned",
    generation: 9,
    ownerLease: "desktop-9",
    dataHome: "/tmp/elfienest",
  });
  const controller = new DesktopRoleController(client);
  await controller.start();

  const result = await controller.maintainOwnedRuntime();

  assert.equal(result.kind, "owned");
  assert.deepEqual(client.recoveries, ["desktop-9"]);
});

test("background maintenance preserves the selected data root without inspecting it again", async () => {
  const client = lifecycleClient({
    kind: "owned",
    generation: 9,
    ownerLease: "desktop-9",
    dataHome: "/tmp/elfienest",
  });
  const controller = new DesktopRoleController(client);
  await controller.start();
  const inspectionsAfterStartup = client.inspections;

  await controller.maintainOwnedRuntime();

  assert.equal(client.inspections, inspectionsAfterStartup);
});

test("background maintenance never takes over an attached external Runtime", async () => {
  const client = lifecycleClient({ kind: "attached", generation: 3, dataHome: "/tmp/elfienest" });
  const controller = new DesktopRoleController(client);
  await controller.start();

  const result = await controller.maintainOwnedRuntime();

  assert.equal(result.kind, "attached");
  assert.deepEqual(client.recoveries, []);
});
