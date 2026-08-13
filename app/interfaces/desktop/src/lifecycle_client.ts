import { execFile } from "node:child_process";
import { join } from "node:path";
import { promisify } from "node:util";

import type {
  LifecycleClient,
  RuntimeAttachment,
} from "./desktop_role_lifecycle.js";

type RuntimeStatus = Readonly<{
  readonly state: "ready" | "degraded" | "starting" | "stopped" | "failed";
  readonly generation: number;
  readonly ownerLease: string | null;
}>;

export interface LifecycleCommandRunner {
  run(argumentsList: readonly string[]): Promise<string>;
}

export class LifecycleClientError extends Error {
  readonly name = "LifecycleClientError";

  constructor(readonly detail: string) {
    super(detail);
  }
}

const runFile = promisify(execFile);

export function lifecycleCommandExecutable(
  isPackaged: boolean,
  resourcesPath: string,
  platform: NodeJS.Platform,
): string {
  if (!isPackaged) {
    return "elfienest";
  }
  const executable = platform === "win32" ? "ElfieNestCli.exe" : "ElfieNestCli";
  return join(resourcesPath, "management-cli", executable);
}

export class ProcessLifecycleCommandRunner implements LifecycleCommandRunner {
  constructor(private readonly executable: string = "elfienest") {}

  async run(argumentsList: readonly string[]): Promise<string> {
    const result = await runFile(this.executable, [...argumentsList]);
    return result.stdout;
  }
}

export class ManagedRuntimeLifecycleClient implements LifecycleClient {
  constructor(
    private readonly ownerLease: string,
    private readonly commandRunner: LifecycleCommandRunner = new ProcessLifecycleCommandRunner(),
  ) {}

  async attachOrStart(): Promise<RuntimeAttachment> {
    try {
      const initial = await this.status();
      if (this.isReady(initial)) {
        if (initial.ownerLease === null) {
          return this.failure(
            "Another ElfieNest checkout is using the service ports; Desktop refused to attach to its data",
          );
        }
        return { kind: "attached", generation: initial.generation };
      }
      if (initial.state === "starting") {
        return this.failure("Runtime is already starting");
      }
      await this.commandRunner.run(["start", "--owner-id", this.ownerLease]);
      const started = await this.status();
      if (this.isReady(started) && started.ownerLease === this.ownerLease) {
        return {
          kind: "owned",
          generation: started.generation,
          ownerLease: this.ownerLease,
        };
      }
      return this.failure("Runtime did not grant the desktop owner lease");
    } catch (error: unknown) {
      return this.failure(this.errorMessage(error));
    }
  }

  async stopOwnedRuntime(ownerLease: string): Promise<void> {
    if (ownerLease !== this.ownerLease) {
      throw new LifecycleClientError("Desktop cannot stop a lease it did not create");
    }
    await this.commandRunner.run(["stop", "--owner-id", ownerLease]);
  }

  async recoverOwnedRuntime(ownerLease: string): Promise<RuntimeAttachment> {
    if (ownerLease !== this.ownerLease) {
      return this.failure("Desktop cannot recover a lease it did not create");
    }
    try {
      const current = await this.status();
      if (this.isReady(current) && current.ownerLease === ownerLease) {
        return this.ownedAttachment(current);
      }
      if (current.state === "starting" && current.ownerLease === ownerLease) {
        return this.ownedAttachment(current);
      }
      if (current.ownerLease !== null && current.ownerLease !== ownerLease) {
        return this.failure("Runtime owner lease changed; recovery refused");
      }
      await this.commandRunner.run(["stop", "--owner-id", ownerLease]);
      await this.commandRunner.run(["start", "--owner-id", ownerLease]);
      const restarted = await this.status();
      if (this.isReady(restarted) && restarted.ownerLease === ownerLease) {
        return this.ownedAttachment(restarted);
      }
      return this.failure("Owned Runtime recovery did not restore full health");
    } catch (error: unknown) {
      return this.failure(this.errorMessage(error));
    }
  }

  private async status(): Promise<RuntimeStatus> {
    const output = await this.commandRunner.run(["status", "--json"]);
    return this.parseStatus(output);
  }

  private parseStatus(output: string): RuntimeStatus {
    let payload: unknown;
    try {
      payload = JSON.parse(output);
    } catch (error: unknown) {
      throw new LifecycleClientError(`Lifecycle status was not JSON: ${this.errorMessage(error)}`);
    }
    if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
      throw new LifecycleClientError("Lifecycle status payload must be an object");
    }
    const state = Reflect.get(payload, "state");
    const generation = Reflect.get(payload, "generation");
    const ownerLease = Reflect.get(payload, "owner_lease");
    if (
      !this.isLifecycleState(state) ||
      typeof generation !== "number" ||
      !Number.isInteger(generation) ||
      generation < 0
    ) {
      throw new LifecycleClientError("Lifecycle status payload is invalid");
    }
    if (ownerLease === null) {
      return { state, generation, ownerLease: null };
    }
    if (
      typeof ownerLease !== "object" ||
      ownerLease === null ||
      !("owner_id" in ownerLease) ||
      typeof ownerLease.owner_id !== "string" ||
      ownerLease.owner_id === ""
    ) {
      throw new LifecycleClientError("Lifecycle status owner lease is invalid");
    }
    return { state, generation, ownerLease: ownerLease.owner_id };
  }

  private isLifecycleState(value: unknown): value is RuntimeStatus["state"] {
    return (
      value === "ready" ||
      value === "degraded" ||
      value === "starting" ||
      value === "stopped" ||
      value === "failed"
    );
  }

  private isReady(status: RuntimeStatus): boolean {
    return status.state === "ready" || status.state === "degraded";
  }

  private ownedAttachment(status: RuntimeStatus): RuntimeAttachment {
    return {
      kind: "owned",
      generation: status.generation,
      ownerLease: this.ownerLease,
    };
  }

  private failure(reason: string): RuntimeAttachment {
    return { kind: "failed", reason, recoverable: true };
  }

  private errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : "Lifecycle command failed";
  }
}
