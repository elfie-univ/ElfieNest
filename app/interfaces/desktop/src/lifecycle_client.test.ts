import { strict as assert } from "node:assert";
import test from "node:test";

import {
  lifecycleCommandFailureDetail,
  lifecycleCommandExecutable,
  ManagedRuntimeLifecycleClient,
  type LifecycleCommandRunner,
} from "./lifecycle_client.js";

type CommandCall = Readonly<{
  readonly argumentsList: readonly string[];
}>;

function commandRunner(
  outputs: readonly string[],
): LifecycleCommandRunner & { readonly calls: CommandCall[] } {
  const calls: CommandCall[] = [];
  let outputIndex = 0;
  return {
    calls,
    run: async (argumentsList: readonly string[]): Promise<string> => {
      calls.push({ argumentsList });
      const output = outputs[outputIndex];
      outputIndex += 1;
      if (output === undefined) {
        throw new Error("unexpected lifecycle command");
      }
      return output;
    },
  };
}

const READY_DATA_HOME = JSON.stringify({
  state: "ready",
  home: "/Users/test/.elfienest",
  detail: "ready",
  recoverable: false,
});

async function selectTestDataHome(
  client: ManagedRuntimeLifecycleClient,
): Promise<void> {
  await client.inspectDataHome();
}

test("packaged Desktop invokes its embedded management CLI", () => {
  assert.equal(
    lifecycleCommandExecutable(true, "/Applications/ElfieNest.app/Contents/Resources", "darwin"),
    "/Applications/ElfieNest.app/Contents/Resources/management-cli/ElfieNestCli",
  );
  assert.equal(
    lifecycleCommandExecutable(true, "C:\\ElfieNest\\resources", "win32"),
    "C:\\ElfieNest\\resources/management-cli/ElfieNestCli.exe",
  );
  assert.equal(lifecycleCommandExecutable(false, "/unused", "darwin"), "elfienest");
});

test("lifecycle command errors preserve a structured stdout diagnostic", () => {
  assert.equal(
    lifecycleCommandFailureDetail(
      '{"event":"runtime_progress","phase":"authority_starting"}\n{"error":"Godot authority failed to become ready"}\n',
      "",
      1,
      null,
    ),
    "Godot authority failed to become ready",
  );
});

test("lifecycle command errors prefer stderr over stdout", () => {
  assert.equal(
    lifecycleCommandFailureDetail("stdout diagnostic", "permission denied", 1, null),
    "permission denied",
  );
});

test("managed lifecycle client inspects the selected data root before startup", async () => {
  const runner = commandRunner([
    JSON.stringify({
      state: "legacy",
      home: "/Users/test/.elfienest",
      detail: "检测到旧版数据目录结构",
      recoverable: true,
    }),
  ]);
  const client = new ManagedRuntimeLifecycleClient("desktop-inspect", runner);

  const inspection = await client.inspectDataHome();

  assert.deepEqual(inspection, {
    state: "legacy",
    home: "/Users/test/.elfienest",
    detail: "检测到旧版数据目录结构",
    recoverable: true,
  });
  assert.deepEqual(runner.calls, [
    { argumentsList: ["--__controller-action", "inspect-data-home"] },
  ]);
});

test("managed lifecycle client accepts a partial data-root inspection", async () => {
  const runner = commandRunner([
    JSON.stringify({
      state: "partial",
      home: "/Users/test/.elfienest",
      detail: "启动时可以补齐缺少的当前数据表",
      recoverable: false,
    }),
  ]);
  const client = new ManagedRuntimeLifecycleClient("desktop-partial", runner);

  const inspection = await client.inspectDataHome();

  assert.equal(inspection.state, "partial");
  assert.equal(inspection.recoverable, false);
});

test("managed lifecycle client recovers a data root through the internal Controller API", async () => {
  const runner = commandRunner([
    JSON.stringify({
      state: "recovered",
      home: "/Users/test/.elfienest",
      backup_home: "/Users/test/.elfienest-backups/legacy",
    }),
  ]);
  const client = new ManagedRuntimeLifecycleClient("desktop-recover", runner);

  const recovery = await client.recoverDataHome();

  assert.deepEqual(recovery, {
    home: "/Users/test/.elfienest",
    backupHome: "/Users/test/.elfienest-backups/legacy",
  });
  assert.deepEqual(runner.calls, [
    { argumentsList: ["--__controller-action", "recover-data-home"] },
  ]);
});

test("managed lifecycle client attaches to a ready CLI-owned Runtime without starting it", async () => {
  // Given: the public CLI reports a ready Runtime leased by CLI.
  const runner = commandRunner([
    READY_DATA_HOME,
    JSON.stringify({ state: "world_ready", tier: "world_ready", phase: "world_ready", generation: 11, owner_lease: { owner_id: "cli" } }),
  ]);
  const client = new ManagedRuntimeLifecycleClient("desktop-11", runner);

  // When: the UI requests a Runtime attachment.
  await selectTestDataHome(client);
  const attachment = await client.attachOrStart();

  // Then: it attaches and leaves the existing owner untouched.
  assert.deepEqual(attachment, { kind: "attached", generation: 11, dataHome: "/Users/test/.elfienest" });
  assert.deepEqual(runner.calls, [
    { argumentsList: ["--__controller-action", "inspect-data-home"] },
    { argumentsList: ["status", "--json"] },
  ]);
});

test("managed lifecycle client refuses an external checkout without a verified owner lease", async () => {
  // Given: another checkout already serves the Core, without a Desktop owner lease.
  const runner = commandRunner([
    JSON.stringify({ state: "core_ready", tier: "core_ready", phase: "failed", generation: 0, owner_lease: null }),
  ]);
  const client = new ManagedRuntimeLifecycleClient("desktop-external", runner);

  // When: packaged Desktop requests an attachment.
  const attachment = await client.attachOrStart();

  // Then: it neither displays the other checkout's data nor tries to own a second Core.
  assert.equal(attachment.kind, "failed");
  if (attachment.kind === "failed") {
    assert.match(attachment.reason, /refused to attach/);
  }
  assert.deepEqual(runner.calls, [{ argumentsList: ["status", "--json"] }]);
});

test("managed lifecycle client starts a stopped Runtime with its desktop lease", async () => {
  // Given: no Runtime exists before the UI session starts.
  const runner = commandRunner([
    READY_DATA_HOME,
    JSON.stringify({ state: "offline", tier: "offline", phase: "offline", generation: 0, owner_lease: null }),
    JSON.stringify({
      state: "world_ready",
      tier: "world_ready",
      phase: "world_ready",
      generation: 12,
      owner_lease: { owner_id: "desktop-12" },
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18234 }],
    }),
  ]);
  const client = new ManagedRuntimeLifecycleClient("desktop-12", runner);

  // When: the UI attaches or starts the managed Runtime.
  await selectTestDataHome(client);
  const attachment = await client.attachOrStart();

  // Then: it receives an owner lease only after the post-start status verifies it.
  assert.deepEqual(attachment, {
    kind: "owned",
    generation: 12,
    ownerLease: "desktop-12",
    dataHome: "/Users/test/.elfienest",
    httpUrl: "http://127.0.0.1:18234/",
  });
  assert.deepEqual(runner.calls, [
    { argumentsList: ["--__controller-action", "inspect-data-home"] },
    { argumentsList: ["status", "--json"] },
    { argumentsList: ["start", "--owner-id", "desktop-12", "--json"] },
  ]);
});

test("managed lifecycle client attaches after another owner finishes startup", async () => {
  const runner = commandRunner([
    READY_DATA_HOME,
    JSON.stringify({
      state: "offline",
      tier: "offline",
      phase: "core_starting",
      generation: 14,
      owner_lease: null,
      startup_owner_id: "cli",
    }),
    JSON.stringify({
      state: "core_ready",
      tier: "core_ready",
      phase: "core_ready",
      generation: 14,
      owner_lease: { owner_id: "cli" },
    }),
  ]);
  const client = new ManagedRuntimeLifecycleClient("desktop-14", runner);

  await selectTestDataHome(client);
  const attachment = await client.attachOrStart();

  assert.deepEqual(attachment, { kind: "attached", generation: 14, dataHome: "/Users/test/.elfienest" });
  assert.deepEqual(runner.calls, [
    { argumentsList: ["--__controller-action", "inspect-data-home"] },
    { argumentsList: ["status", "--json"] },
    { argumentsList: ["status", "--json"] },
  ]);
});

test("managed lifecycle client preserves the authoritative startup failure detail", async () => {
  const runner = commandRunner([
    JSON.stringify({
      state: "offline",
      tier: "offline",
      phase: "core_starting",
      generation: 15,
      owner_lease: null,
      startup_owner_id: "cli",
    }),
    JSON.stringify({
      state: "offline",
      tier: "offline",
      phase: "failed",
      generation: 15,
      owner_lease: null,
      failures: [{ code: "START_FAILED", detail: "Godot WebSocket port is unavailable" }],
    }),
  ]);
  const client = new ManagedRuntimeLifecycleClient("desktop-15", runner);

  const attachment = await client.attachOrStart();

  assert.deepEqual(attachment, {
    kind: "failed",
    reason: "Godot WebSocket port is unavailable",
    recoverable: true,
  });
});

test("managed lifecycle client streams Core-ready progress before full Runtime readiness", async () => {
  const calls: CommandCall[] = [];
  const phases: string[] = [];
  const runWithProgress = async (
    argumentsList: readonly string[],
    onLine: (line: string) => void,
  ): Promise<string> => {
    calls.push({ argumentsList });
    const coreReady = JSON.stringify({ event: "runtime_progress", phase: "core_ready" });
    const authorityStarting = JSON.stringify({ event: "runtime_progress", phase: "authority_starting" });
    onLine(coreReady);
    onLine(authorityStarting);
    const status = JSON.stringify({
      state: "world_ready",
      tier: "world_ready",
      phase: "world_ready",
      generation: 13,
      owner_lease: { owner_id: "desktop-13" },
      startup_owner_id: null,
    });
    return `${coreReady}\n${authorityStarting}\n${status}\n`;
  };
  const initial = commandRunner([
    READY_DATA_HOME,
    JSON.stringify({ state: "offline", tier: "offline", phase: "offline", generation: 0, owner_lease: null }),
  ]);
  const statusCalls = initial.calls;
  const composedRunner: LifecycleCommandRunner = {
    run: initial.run,
    runWithProgress,
  };
  const composedClient = new ManagedRuntimeLifecycleClient("desktop-13", composedRunner);

  await selectTestDataHome(composedClient);
  const attachment = await composedClient.attachOrStart((phase) => phases.push(phase));

  assert.deepEqual(attachment, { kind: "owned", generation: 13, ownerLease: "desktop-13", dataHome: "/Users/test/.elfienest" });
  assert.deepEqual(phases, ["core_ready", "authority_starting"]);
  assert.deepEqual(statusCalls, [
    { argumentsList: ["--__controller-action", "inspect-data-home"] },
    { argumentsList: ["status", "--json"] },
  ]);
  assert.deepEqual(calls, [{ argumentsList: ["start", "--owner-id", "desktop-13", "--json", "--progress-json"] }]);
});

test("managed lifecycle client sends a lease-scoped stop request", async () => {
  // Given: a desktop-owned Runtime lease.
  const runner = commandRunner(["stopped"]);
  const client = new ManagedRuntimeLifecycleClient("desktop-13", runner);

  // When: explicit application exit stops that Runtime.
  await client.stopOwnedRuntime("desktop-13");

  // Then: only the matching owner lease is sent to the public lifecycle command.
  assert.deepEqual(runner.calls, [
    { argumentsList: ["stop", "--owner-id", "desktop-13"] },
  ]);
});

test("managed lifecycle client cancels an in-flight start through the public stop command", async () => {
  const runner = commandRunner(["✅ Service stopped"]);
  const client = new ManagedRuntimeLifecycleClient("desktop-cancel", runner);

  await client.cancelStart();

  assert.deepEqual(runner.calls, [
    { argumentsList: ["stop", "--owner-id", "desktop-cancel"] },
  ]);
});

test("managed lifecycle client keeps the owned Core after authority failure", async () => {
  const runner = commandRunner([
    READY_DATA_HOME,
    JSON.stringify({
      state: "core_ready",
      tier: "core_ready",
      phase: "failed",
      generation: 14,
      owner_lease: { owner_id: "desktop-14" },
    }),
  ]);
  const client = new ManagedRuntimeLifecycleClient("desktop-14", runner);

  await selectTestDataHome(client);
  const attachment = await client.recoverOwnedRuntime("desktop-14");

  assert.deepEqual(attachment, {
    kind: "owned",
    generation: 14,
    ownerLease: "desktop-14",
    dataHome: "/Users/test/.elfienest",
  });
  assert.deepEqual(runner.calls, [
    { argumentsList: ["--__controller-action", "inspect-data-home"] },
    { argumentsList: ["status", "--json"] },
  ]);
});

test("managed lifecycle client refuses to recover another owner's Runtime", async () => {
  const runner = commandRunner([
    JSON.stringify({
      state: "core_ready",
      tier: "core_ready",
      phase: "failed",
      generation: 16,
      owner_lease: { owner_id: "cli" },
    }),
  ]);
  const client = new ManagedRuntimeLifecycleClient("desktop-16", runner);

  const attachment = await client.recoverOwnedRuntime("desktop-16");

  assert.equal(attachment.kind, "failed");
  assert.deepEqual(runner.calls, [{ argumentsList: ["status", "--json"] }]);
});
