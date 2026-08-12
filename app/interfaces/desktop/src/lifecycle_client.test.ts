import { strict as assert } from "node:assert";
import test from "node:test";

import {
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

test("managed lifecycle client attaches to a ready CLI-owned Runtime without starting it", async () => {
  // Given: the public CLI reports a ready Runtime leased by CLI.
  const runner = commandRunner([
    JSON.stringify({ state: "ready", generation: 11, owner_lease: { owner_id: "cli" } }),
  ]);
  const client = new ManagedRuntimeLifecycleClient("desktop-11", runner);

  // When: the UI requests a Runtime attachment.
  const attachment = await client.attachOrStart();

  // Then: it attaches and leaves the existing owner untouched.
  assert.deepEqual(attachment, { kind: "attached", generation: 11 });
  assert.deepEqual(runner.calls, [{ argumentsList: ["status", "--json"] }]);
});

test("managed lifecycle client starts a stopped Runtime with its desktop lease", async () => {
  // Given: no Runtime exists before the UI session starts.
  const runner = commandRunner([
    JSON.stringify({ state: "stopped", generation: 0, owner_lease: null }),
    "started",
    JSON.stringify({ state: "ready", generation: 12, owner_lease: { owner_id: "desktop-12" } }),
  ]);
  const client = new ManagedRuntimeLifecycleClient("desktop-12", runner);

  // When: the UI attaches or starts the managed Runtime.
  const attachment = await client.attachOrStart();

  // Then: it receives an owner lease only after the post-start status verifies it.
  assert.deepEqual(attachment, { kind: "owned", generation: 12, ownerLease: "desktop-12" });
  assert.deepEqual(runner.calls, [
    { argumentsList: ["status", "--json"] },
    { argumentsList: ["start", "--owner-id", "desktop-12"] },
    { argumentsList: ["status", "--json"] },
  ]);
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
