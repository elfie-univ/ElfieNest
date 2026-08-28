import { strict as assert } from "node:assert";
import test from "node:test";

import {
  classifyRuntimeHealthPayload,
  lifecycleCommandFailureDetail,
  lifecycleCommandExecutable,
  ManagedRuntimeLifecycleClient,
  probeRuntimeHealth,
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

test("an explicit retry retains ownership of its already-ready lease", async () => {
  const runner = commandRunner([
    READY_DATA_HOME,
    JSON.stringify({
      instance_id: "runtime-owned-retry",
      state: "world_ready",
      tier: "world_ready",
      phase: "world_ready",
      generation: 12,
      owner_lease: { owner_id: "desktop-retry" },
      components: [{ name: "core", state: "ready", pid: 7012 }],
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18112 }],
    }),
  ]);
  const client = new ManagedRuntimeLifecycleClient("desktop-retry", runner);

  await selectTestDataHome(client);
  const attachment = await client.attachOrStart();

  assert.deepEqual(attachment, {
    kind: "owned",
    generation: 12,
    ownerLease: "desktop-retry",
    dataHome: "/Users/test/.elfienest",
    httpUrl: "http://127.0.0.1:18112/",
  });
});

test("managed lifecycle client refuses an external checkout without a verified owner lease", async () => {
  // Given: another checkout already serves the Core, without a Desktop owner lease.
  const runner = commandRunner([
    JSON.stringify({
      state: "core_ready",
      tier: "core_ready",
      phase: "failed",
      generation: 0,
      owner_lease: null,
      instance_id: "runtime-external",
      components: [{ name: "core", state: "ready", pid: 7000 }],
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18100 }],
    }),
  ]);
  const client = new ManagedRuntimeLifecycleClient(
    "desktop-external",
    runner,
    async () => ({ kind: "healthy" }),
    () => "alive",
  );

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
      instance_id: "runtime-instance-14",
      state: "offline",
      tier: "offline",
      phase: "core_starting",
      generation: 14,
      owner_lease: null,
      startup_owner_id: "cli",
    }),
    JSON.stringify({
      instance_id: "runtime-instance-14",
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
    {
      argumentsList: [
        "--__controller-action",
        "wait-runtime",
        "--__controller-data-home",
        "/Users/test/.elfienest",
        "--__controller-instance-id",
        "runtime-instance-14",
        "--__controller-generation",
        "14",
      ],
    },
  ]);
});

test("managed lifecycle client preserves the authoritative startup failure detail", async () => {
  const runner = commandRunner([
    READY_DATA_HOME,
    JSON.stringify({
      instance_id: "runtime-instance-15",
      state: "offline",
      tier: "offline",
      phase: "core_starting",
      generation: 15,
      owner_lease: null,
      startup_owner_id: "cli",
    }),
    JSON.stringify({
      instance_id: "runtime-instance-15",
      state: "offline",
      tier: "offline",
      phase: "failed",
      generation: 15,
      owner_lease: null,
      failures: [{ code: "START_FAILED", detail: "Godot WebSocket port is unavailable" }],
    }),
  ]);
  const client = new ManagedRuntimeLifecycleClient("desktop-15", runner);

  await selectTestDataHome(client);
  const attachment = await client.attachOrStart();

  assert.deepEqual(attachment, {
    kind: "failed",
    reason: "Godot WebSocket port is unavailable",
    recoverable: true,
  });
  assert.deepEqual(runner.calls, [
    { argumentsList: ["--__controller-action", "inspect-data-home"] },
    { argumentsList: ["status", "--json"] },
    {
      argumentsList: [
        "--__controller-action",
        "wait-runtime",
        "--__controller-data-home",
        "/Users/test/.elfienest",
        "--__controller-instance-id",
        "runtime-instance-15",
        "--__controller-generation",
        "15",
      ],
    },
  ]);
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
      state: "offline",
      tier: "offline",
      phase: "offline",
      generation: 0,
      owner_lease: null,
    }),
    JSON.stringify({
      instance_id: "runtime-instance-14",
      state: "core_ready",
      tier: "core_ready",
      phase: "failed",
      generation: 14,
      owner_lease: { owner_id: "desktop-14" },
      components: [{ name: "core", state: "ready", pid: 7014 }],
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18114 }],
    }),
  ]);
  const client = new ManagedRuntimeLifecycleClient(
    "desktop-14",
    runner,
    async () => ({ kind: "healthy" }),
    () => "alive",
  );

  await selectTestDataHome(client);
  await client.attachOrStart();
  const callsAfterStartup = runner.calls.length;
  const attachment = await client.recoverOwnedRuntime("desktop-14");

  assert.deepEqual(attachment, {
    kind: "owned",
    generation: 14,
    ownerLease: "desktop-14",
    dataHome: "/Users/test/.elfienest",
    httpUrl: "http://127.0.0.1:18114/",
  });
  assert.equal(runner.calls.length, callsAfterStartup);
});

test("managed lifecycle client refuses a stale failed Core projection from another owner", async () => {
  const runner = commandRunner([
    JSON.stringify({
      state: "core_ready",
      tier: "core_ready",
      phase: "failed",
      generation: 15,
      owner_lease: { owner_id: "desktop-other" },
      instance_id: "runtime-instance-15",
      components: [{ name: "core", state: "ready", pid: 7015 }],
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18115 }],
    }),
  ]);
  const client = new ManagedRuntimeLifecycleClient(
    "desktop-stale",
    runner,
    async () => ({ kind: "transport_failure", detail: "connection refused" }),
    () => "absent",
  );

  const attachment = await client.attachOrStart();

  assert.equal(attachment.kind, "failed");
  assert.deepEqual(runner.calls, [{ argumentsList: ["status", "--json"] }]);
});

test("repeated healthy owned Runtime maintenance does not launch the management CLI", async () => {
  const runner = commandRunner([
    READY_DATA_HOME,
    JSON.stringify({
      state: "offline",
      tier: "offline",
      phase: "offline",
      generation: 0,
      owner_lease: null,
    }),
    JSON.stringify({
      instance_id: "runtime-instance-17",
      state: "world_ready",
      tier: "world_ready",
      phase: "world_ready",
      generation: 17,
      owner_lease: { owner_id: "desktop-17" },
      components: [{ name: "core", state: "ready", pid: 7017 }],
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18117 }],
    }),
  ]);
  const probes: Array<Readonly<{
    httpUrl: string;
    instanceId: string;
    generation: number;
  }>> = [];
  const client = new ManagedRuntimeLifecycleClient(
    "desktop-17",
    runner,
    async (target) => {
      probes.push(target);
      return { kind: "healthy" };
    },
  );
  await selectTestDataHome(client);
  const started = await client.attachOrStart();
  assert.equal(started.kind, "owned");
  const callsAfterStartup = runner.calls.length;

  const maintained = [
    await client.recoverOwnedRuntime("desktop-17"),
    await client.recoverOwnedRuntime("desktop-17"),
    await client.recoverOwnedRuntime("desktop-17"),
  ];

  assert.deepEqual(maintained, [started, started, started]);
  assert.equal(runner.calls.length, callsAfterStartup);
  assert.deepEqual(probes, Array.from({ length: 3 }, () => ({
    httpUrl: "http://127.0.0.1:18117/",
    instanceId: "runtime-instance-17",
    generation: 17,
  })));
});

test("Core health classification does not take over World recovery", () => {
  const target = {
    httpUrl: "http://127.0.0.1:18117/",
    instanceId: "runtime-instance-17",
    generation: 17,
  };

  assert.deepEqual(classifyRuntimeHealthPayload({
    status: "ok",
    engine_ready: true,
    godot_runtime_ready: false,
    instance_id: "runtime-instance-17",
    generation: 17,
  }, target), { kind: "healthy" });
  assert.equal(classifyRuntimeHealthPayload({
    status: "ok",
    engine_ready: false,
    godot_runtime_ready: false,
    instance_id: "runtime-instance-17",
    generation: 17,
  }, target).kind, "transitioning");
  assert.equal(classifyRuntimeHealthPayload({
    status: "ok",
    engine_ready: true,
    instance_id: "another-runtime",
    generation: 17,
  }, target).kind, "identity_mismatch");
  assert.equal(classifyRuntimeHealthPayload({
    status: "ok",
    engine_ready: true,
    instance_id: "runtime-instance-17",
    generation: 18,
  }, target).kind, "identity_mismatch");
  assert.equal(classifyRuntimeHealthPayload({
    status: "ok",
    engine_ready: "yes",
    instance_id: "runtime-instance-17",
    generation: 17,
  }, target).kind, "protocol_invalid");
});

test("Runtime health probe calls the Core health endpoint and verifies identity", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl: string | undefined;
  globalThis.fetch = async (input, init): Promise<Response> => {
    requestedUrl = String(input);
    assert.equal(init?.cache, "no-store");
    assert.equal(init?.redirect, "error");
    assert.ok(init?.signal instanceof AbortSignal);
    return new Response(JSON.stringify({
      status: "ok",
      engine_ready: true,
      godot_runtime_ready: false,
      instance_id: "runtime-instance-17",
      generation: 17,
    }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  try {
    assert.deepEqual(await probeRuntimeHealth({
      httpUrl: "http://127.0.0.1:18117/",
      instanceId: "runtime-instance-17",
      generation: 17,
    }), { kind: "healthy" });
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(requestedUrl, "http://127.0.0.1:18117/api/health");
});

test("ten transient Core transport failures do not launch the CLI", async () => {
  const runner = commandRunner([
    READY_DATA_HOME,
    JSON.stringify({
      state: "offline",
      tier: "offline",
      phase: "offline",
      generation: 0,
      owner_lease: null,
    }),
    JSON.stringify({
      instance_id: "runtime-instance-17",
      state: "world_ready",
      tier: "world_ready",
      phase: "world_ready",
      generation: 17,
      owner_lease: { owner_id: "desktop-17" },
      components: [{ name: "core", state: "ready", pid: 7017 }],
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18117 }],
    }),
  ]);
  const processProbes: number[] = [];
  let now = 0;
  const client = new ManagedRuntimeLifecycleClient(
    "desktop-17",
    runner,
    async () => ({ kind: "transport_failure", detail: "timed out" }),
    (pid) => {
      processProbes.push(pid);
      return "alive";
    },
    () => now,
  );
  await selectTestDataHome(client);
  const started = await client.attachOrStart();
  const callsAfterStartup = runner.calls.length;

  const maintained = [];
  for (let index = 0; index < 10; index += 1) {
    maintained.push(await client.recoverOwnedRuntime("desktop-17"));
    now += 5_000;
  }

  assert.deepEqual(maintained, Array.from({ length: 10 }, () => started));
  assert.equal(runner.calls.length, callsAfterStartup);
  assert.deepEqual(processProbes, Array.from({ length: 10 }, () => 7017));
});

test("a known dead Core process triggers one atomic lease-scoped recovery", async () => {
  const runner = commandRunner([
    READY_DATA_HOME,
    JSON.stringify({
      state: "offline",
      tier: "offline",
      phase: "offline",
      generation: 0,
      owner_lease: null,
    }),
    JSON.stringify({
      instance_id: "runtime-instance-18",
      state: "world_ready",
      tier: "world_ready",
      phase: "world_ready",
      generation: 18,
      owner_lease: { owner_id: "desktop-18" },
      components: [{ name: "core", state: "ready", pid: 7018 }],
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18118 }],
    }),
    JSON.stringify({
      instance_id: "runtime-instance-19",
      state: "world_ready",
      tier: "world_ready",
      phase: "world_ready",
      generation: 19,
      owner_lease: { owner_id: "desktop-18" },
      components: [{ name: "core", state: "ready", pid: 7019 }],
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18119 }],
    }),
  ]);
  const processProbes: number[] = [];
  const client = new ManagedRuntimeLifecycleClient(
    "desktop-18",
    runner,
    async () => ({ kind: "transport_failure", detail: "connection refused" }),
    (pid) => {
      processProbes.push(pid);
      return "absent";
    },
  );
  await selectTestDataHome(client);
  await client.attachOrStart();
  const callsAfterStartup = runner.calls.length;

  const recovered = await client.recoverOwnedRuntime("desktop-18");

  assert.equal(recovered.kind, "owned");
  assert.deepEqual(processProbes, [7018]);
  assert.deepEqual(runner.calls.slice(callsAfterStartup), [
    {
      argumentsList: [
        "--__controller-action",
        "recover-owned",
        "--__controller-data-home",
        "/Users/test/.elfienest",
        "--__controller-owner-id",
        "desktop-18",
        "--__controller-instance-id",
        "runtime-instance-18",
        "--__controller-generation",
        "18",
        "--__controller-core-pid",
        "7018",
        "--__controller-reason",
        "process-absent",
      ],
    },
  ]);
});

test("sustained Core transport failure triggers one atomic recovery after 60 seconds", async () => {
  const currentStatus = {
    instance_id: "runtime-instance-20",
    state: "world_ready",
    tier: "world_ready",
    phase: "world_ready",
    generation: 20,
    owner_lease: { owner_id: "desktop-20" },
    components: [{ name: "core", state: "ready", pid: 7020 }],
    endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18120 }],
  };
  const runner = commandRunner([
    READY_DATA_HOME,
    JSON.stringify({
      state: "offline",
      tier: "offline",
      phase: "offline",
      generation: 0,
      owner_lease: null,
    }),
    JSON.stringify(currentStatus),
    JSON.stringify({
      ...currentStatus,
      instance_id: "runtime-instance-21",
      generation: 21,
      components: [{ name: "core", state: "ready", pid: 7021 }],
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18121 }],
    }),
  ]);
  let now = 0;
  const client = new ManagedRuntimeLifecycleClient(
    "desktop-20",
    runner,
    async () => ({ kind: "transport_failure", detail: "timed out" }),
    () => "alive",
    () => now,
  );
  await selectTestDataHome(client);
  await client.attachOrStart();
  const callsAfterStartup = runner.calls.length;

  await client.recoverOwnedRuntime("desktop-20");
  now = 30_000;
  await client.recoverOwnedRuntime("desktop-20");
  now = 60_000;
  const recovered = await client.recoverOwnedRuntime("desktop-20");
  for (let index = 0; index < 10; index += 1) {
    await client.recoverOwnedRuntime("desktop-20");
  }

  assert.equal(recovered.kind, "owned");
  assert.deepEqual(runner.calls.slice(callsAfterStartup), [
    {
      argumentsList: [
        "--__controller-action",
        "recover-owned",
        "--__controller-data-home",
        "/Users/test/.elfienest",
        "--__controller-owner-id",
        "desktop-20",
        "--__controller-instance-id",
        "runtime-instance-20",
        "--__controller-generation",
        "20",
        "--__controller-core-pid",
        "7020",
        "--__controller-reason",
        "transport-failure",
      ],
    },
  ]);
});

test("an automatically recovered generation cannot start a cross-generation crash loop", async () => {
  const ownedStatus = {
    state: "world_ready",
    tier: "world_ready",
    phase: "world_ready",
    owner_lease: { owner_id: "desktop-loop" },
  } as const;
  const runner = commandRunner([
    READY_DATA_HOME,
    JSON.stringify({
      state: "offline",
      tier: "offline",
      phase: "offline",
      generation: 0,
      owner_lease: null,
    }),
    JSON.stringify({
      ...ownedStatus,
      instance_id: "runtime-loop-30",
      generation: 30,
      components: [{ name: "core", state: "ready", pid: 7030 }],
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18130 }],
    }),
    JSON.stringify({
      ...ownedStatus,
      instance_id: "runtime-loop-31",
      generation: 31,
      components: [{ name: "core", state: "ready", pid: 7031 }],
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18131 }],
    }),
    "stopped",
  ]);
  const client = new ManagedRuntimeLifecycleClient(
    "desktop-loop",
    runner,
    async () => ({ kind: "transport_failure", detail: "connection refused" }),
    () => "absent",
    () => 0,
  );
  await selectTestDataHome(client);
  await client.attachOrStart();
  const callsAfterStartup = runner.calls.length;

  const recovered = await client.recoverOwnedRuntime("desktop-loop");
  const tripped = await client.recoverOwnedRuntime("desktop-loop");
  const repeated = await client.recoverOwnedRuntime("desktop-loop");

  assert.equal(recovered.kind, "owned");
  if (recovered.kind === "owned") {
    assert.equal(recovered.generation, 31);
  }
  assert.equal(tripped.kind, "failed");
  assert.equal(repeated.kind, "failed");
  if (tripped.kind === "failed") {
    assert.match(tripped.reason, /10 minutes of continuous health/u);
  }
  assert.deepEqual(runner.calls.slice(callsAfterStartup), [
    {
      argumentsList: [
        "--__controller-action",
        "recover-owned",
        "--__controller-data-home",
        "/Users/test/.elfienest",
        "--__controller-owner-id",
        "desktop-loop",
        "--__controller-instance-id",
        "runtime-loop-30",
        "--__controller-generation",
        "30",
        "--__controller-core-pid",
        "7030",
        "--__controller-reason",
        "process-absent",
      ],
    },
    { argumentsList: ["stop", "--owner-id", "desktop-loop"] },
  ]);
});

test("ten minutes of continuous recovered-generation health reopens one recovery budget", async () => {
  const ownedStatus = {
    state: "world_ready",
    tier: "world_ready",
    phase: "world_ready",
    owner_lease: { owner_id: "desktop-stable" },
  } as const;
  const runner = commandRunner([
    READY_DATA_HOME,
    JSON.stringify({
      state: "offline",
      tier: "offline",
      phase: "offline",
      generation: 0,
      owner_lease: null,
    }),
    JSON.stringify({
      ...ownedStatus,
      instance_id: "runtime-stable-40",
      generation: 40,
      components: [{ name: "core", state: "ready", pid: 7040 }],
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18140 }],
    }),
    JSON.stringify({
      ...ownedStatus,
      instance_id: "runtime-stable-41",
      generation: 41,
      components: [{ name: "core", state: "ready", pid: 7041 }],
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18141 }],
    }),
    JSON.stringify({
      ...ownedStatus,
      instance_id: "runtime-stable-42",
      generation: 42,
      components: [{ name: "core", state: "ready", pid: 7042 }],
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18142 }],
    }),
  ]);
  let now = 0;
  let probeIndex = 0;
  const client = new ManagedRuntimeLifecycleClient(
    "desktop-stable",
    runner,
    async () => {
      probeIndex += 1;
      return probeIndex === 2 || probeIndex === 3
        ? { kind: "healthy" }
        : { kind: "transport_failure", detail: "connection refused" };
    },
    () => "absent",
    () => now,
  );
  await selectTestDataHome(client);
  await client.attachOrStart();

  const firstRecovery = await client.recoverOwnedRuntime("desktop-stable");
  assert.equal(firstRecovery.kind, "owned");
  if (firstRecovery.kind === "owned") {
    assert.equal(firstRecovery.generation, 41);
  }
  await client.recoverOwnedRuntime("desktop-stable");
  now = 10 * 60_000;
  await client.recoverOwnedRuntime("desktop-stable");
  now += 1;
  const secondRecovery = await client.recoverOwnedRuntime("desktop-stable");

  assert.equal(secondRecovery.kind, "owned");
  if (secondRecovery.kind === "owned") {
    assert.equal(secondRecovery.generation, 42);
  }
  assert.equal(
    runner.calls.filter((call) => call.argumentsList.includes("recover-owned")).length,
    2,
  );
  assert.equal(
    runner.calls.filter((call) => call.argumentsList[0] === "stop").length,
    0,
  );
});

test("identity and protocol failures never launch automatic recovery", async () => {
  const runner = commandRunner([
    READY_DATA_HOME,
    JSON.stringify({
      state: "offline",
      tier: "offline",
      phase: "offline",
      generation: 0,
      owner_lease: null,
    }),
    JSON.stringify({
      instance_id: "runtime-instance-22",
      state: "world_ready",
      tier: "world_ready",
      phase: "world_ready",
      generation: 22,
      owner_lease: { owner_id: "desktop-22" },
      components: [{ name: "core", state: "ready", pid: 7022 }],
      endpoints: [{ name: "http", scheme: "http", host: "127.0.0.1", port: 18122 }],
    }),
  ]);
  let probeIndex = 0;
  let processProbeCount = 0;
  const client = new ManagedRuntimeLifecycleClient(
    "desktop-22",
    runner,
    async () => {
      probeIndex += 1;
      return probeIndex % 2 === 0
        ? { kind: "protocol_invalid", detail: "invalid payload" }
        : { kind: "identity_mismatch", detail: "unexpected generation" };
    },
    () => {
      processProbeCount += 1;
      return "absent";
    },
    () => 600_000,
  );
  await selectTestDataHome(client);
  const started = await client.attachOrStart();
  const callsAfterStartup = runner.calls.length;

  const maintained = [];
  for (let index = 0; index < 10; index += 1) {
    maintained.push(await client.recoverOwnedRuntime("desktop-22"));
  }

  assert.equal(started.kind, "owned");
  assert.ok(maintained.every((attachment) => attachment.kind === "failed"));
  assert.equal(runner.calls.length, callsAfterStartup);
  assert.equal(processProbeCount, 0);
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
  assert.deepEqual(runner.calls, []);
});
