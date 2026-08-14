import { execFile, spawn } from "node:child_process";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { promisify } from "node:util";

import type {
  LifecycleClient,
  RuntimeAttachment,
} from "./desktop_role_lifecycle.js";

type RuntimeStatus = Readonly<{
  readonly state: "ready" | "degraded" | "starting" | "stopping" | "stopped" | "failed";
  readonly generation: number;
  readonly ownerLease: string | null;
  readonly startupOwnerId: string | null;
}>;

export type DataHomeState = "fresh" | "ready" | "legacy" | "corrupt" | "permission";

export type DataHomeInspection = Readonly<{
  readonly state: DataHomeState;
  readonly home: string;
  readonly detail: string;
  readonly recoverable: boolean;
}>;

export type DataHomeRecoveryResult = Readonly<{
  readonly home: string;
  readonly backupHome: string;
}>;

export type RuntimeStartupPhase =
  | "starting"
  | "core_ready"
  | "authority_starting"
  | "ready"
  | "stopping"
  | "failed";

export interface LifecycleCommandRunner {
  run(argumentsList: readonly string[]): Promise<string>;
  runWithProgress?(
    argumentsList: readonly string[],
    onLine: (line: string) => void,
  ): Promise<string>;
}

/**
 * Prefer the CLI's structured or human-readable diagnostic over a generic exit
 * code. The lifecycle CLI writes JSON failures and human diagnostics to
 * stdout, while process/runtime errors are written to stderr.
 */
export function lifecycleCommandFailureDetail(
  stdout: string,
  stderr: string,
  code: number | null,
  signal: NodeJS.Signals | null,
): string {
  const stderrDetail = stderr.trim();
  if (stderrDetail !== "") return stderrDetail;

  const lines = stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line !== "");
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index];
    if (line === undefined) continue;
    try {
      const payload: unknown = JSON.parse(line);
      if (typeof payload === "object" && payload !== null && !Array.isArray(payload)) {
        const detail = Reflect.get(payload, "error");
        if (typeof detail === "string" && detail.trim() !== "") return detail.trim();
        if (Reflect.get(payload, "event") === "runtime_progress") continue;
      }
    } catch {
      // Human-readable CLI output is intentionally handled below.
    }
    return line;
  }
  return `Lifecycle command exited with ${signal ?? code}`;
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
    try {
      const result = await runFile(this.executable, [...argumentsList]);
      return result.stdout;
    } catch (error: unknown) {
      if (!(error instanceof Error)) throw error;
      const processError = error as Error & {
        readonly stdout?: unknown;
        readonly stderr?: unknown;
        readonly code?: unknown;
      };
      const stdout = typeof processError.stdout === "string" ? processError.stdout : "";
      const stderr = typeof processError.stderr === "string" ? processError.stderr : "";
      if (stdout === "" && stderr === "") throw error;
      const code = typeof processError.code === "number" ? processError.code : null;
      throw new Error(
        lifecycleCommandFailureDetail(stdout, stderr, code, null),
      );
    }
  }

  runWithProgress(
    argumentsList: readonly string[],
    onLine: (line: string) => void,
  ): Promise<string> {
    return new Promise((resolve, reject) => {
      const child = spawn(this.executable, [...argumentsList], {
        stdio: ["ignore", "pipe", "pipe"],
      });
      const stdout = child.stdout;
      const stderr = child.stderr;
      if (stdout === null || stderr === null) {
        reject(new Error("Lifecycle progress stream unavailable"));
        return;
      }
      let output = "";
      let errorOutput = "";
      stdout.setEncoding("utf8");
      stderr.setEncoding("utf8");
      stdout.on("data", (chunk: string) => { output += chunk; });
      stderr.on("data", (chunk: string) => { errorOutput += chunk; });
      const lines = createInterface({ input: stdout });
      lines.on("line", onLine);
      child.once("error", reject);
      child.once("close", (code, signal) => {
        lines.close();
        if (code === 0) {
          resolve(output);
          return;
        }
        reject(new Error(lifecycleCommandFailureDetail(output, errorOutput, code, signal)));
      });
    });
  }
}

export class ManagedRuntimeLifecycleClient implements LifecycleClient {
  constructor(
    private readonly ownerLease: string,
    private readonly commandRunner: LifecycleCommandRunner = new ProcessLifecycleCommandRunner(),
  ) {}

  async inspectDataHome(explicitHome?: string): Promise<DataHomeInspection> {
    return this.parseDataHomeInspection(
      await this.commandRunner.run(this.dataHomeArguments("inspect", explicitHome)),
    );
  }

  async recoverDataHome(explicitHome?: string): Promise<DataHomeRecoveryResult> {
    return this.parseDataHomeRecovery(
      await this.commandRunner.run(this.dataHomeArguments("recover", explicitHome)),
    );
  }

  async activateDataHome(explicitHome: string): Promise<DataHomeInspection> {
    return this.parseDataHomeInspection(
      await this.commandRunner.run(this.dataHomeArguments("activate", explicitHome)),
    );
  }

  async attachOrStart(
    onProgress?: (phase: RuntimeStartupPhase) => void,
  ): Promise<RuntimeAttachment> {
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
        return this.failure(
          initial.startupOwnerId === null
            ? "Runtime is already starting"
            : "Runtime is already starting under another owner",
        );
      }
      const startArguments = [
        "start",
        "--owner-id",
        this.ownerLease,
        "--json",
        ...(onProgress !== undefined && this.commandRunner.runWithProgress !== undefined
          ? ["--progress-json"]
          : []),
      ] as const;
      const output = onProgress !== undefined && this.commandRunner.runWithProgress !== undefined
        ? await this.commandRunner.runWithProgress(
          startArguments,
          (line) => this.handleProgressLine(line, onProgress),
        )
        : await this.commandRunner.run(startArguments);
      const started = this.parseStatus(output);
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

  async cancelStart(): Promise<void> {
    await this.commandRunner.run(["stop", "--owner-id", this.ownerLease]);
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
      const restarted = this.parseStatus(
        await this.commandRunner.run(["start", "--owner-id", ownerLease, "--json"]),
      );
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
      const lines = output
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter((line) => line !== "");
      for (let index = lines.length - 1; index >= 0; index -= 1) {
        const line = lines[index];
        if (line === undefined) continue;
        try {
          const candidate: unknown = JSON.parse(line);
          if (
            typeof candidate === "object"
            && candidate !== null
            && !Array.isArray(candidate)
            && Reflect.has(candidate, "state")
          ) {
            payload = candidate;
            break;
          }
        } catch {
          // Ignore progress or human-readable lines and inspect the next one.
        }
      }
      if (payload === undefined) {
        throw new LifecycleClientError(`Lifecycle status was not JSON: ${this.errorMessage(error)}`);
      }
    }
    if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
      throw new LifecycleClientError("Lifecycle status payload must be an object");
    }
    const state = Reflect.get(payload, "state");
    const generation = Reflect.get(payload, "generation");
    const ownerLease = Reflect.get(payload, "owner_lease");
    const startupOwnerId = Reflect.get(payload, "startup_owner_id");
    if (
      !this.isLifecycleState(state) ||
      typeof generation !== "number" ||
      !Number.isInteger(generation) ||
      generation < 0
    ) {
      throw new LifecycleClientError("Lifecycle status payload is invalid");
    }
    if (
      startupOwnerId !== undefined
      && startupOwnerId !== null
      && typeof startupOwnerId !== "string"
    ) {
      throw new LifecycleClientError("Lifecycle startup owner is invalid");
    }
    if (ownerLease === null) {
      return {
        state,
        generation,
        ownerLease: null,
        startupOwnerId: typeof startupOwnerId === "string" ? startupOwnerId : null,
      };
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
    return {
      state,
      generation,
      ownerLease: ownerLease.owner_id,
      startupOwnerId: typeof startupOwnerId === "string" ? startupOwnerId : null,
    };
  }

  private handleProgressLine(
    line: string,
    onProgress: (phase: RuntimeStartupPhase) => void,
  ): void {
    let payload: unknown;
    try {
      payload = JSON.parse(line);
    } catch {
      return;
    }
    if (typeof payload !== "object" || payload === null || Array.isArray(payload)) return;
    if (Reflect.get(payload, "event") !== "runtime_progress") return;
    const phase = Reflect.get(payload, "phase");
    if (this.isStartupPhase(phase)) onProgress(phase);
  }

  private parseDataHomeInspection(output: string): DataHomeInspection {
    const payload = this.parseJsonObject(output, "Data-home inspection was not JSON");
    const state = Reflect.get(payload, "state");
    const home = Reflect.get(payload, "home");
    const detail = Reflect.get(payload, "detail");
    const recoverable = Reflect.get(payload, "recoverable");
    if (
      !this.isDataHomeState(state)
      || typeof home !== "string"
      || home === ""
      || typeof detail !== "string"
      || typeof recoverable !== "boolean"
    ) {
      throw new LifecycleClientError("Data-home inspection payload is invalid");
    }
    return { state, home, detail, recoverable };
  }

  private parseDataHomeRecovery(output: string): DataHomeRecoveryResult {
    const payload = this.parseJsonObject(output, "Data-home recovery was not JSON");
    const home = Reflect.get(payload, "home");
    const backupHome = Reflect.get(payload, "backup_home");
    if (
      typeof home !== "string"
      || home === ""
      || typeof backupHome !== "string"
      || backupHome === ""
    ) {
      throw new LifecycleClientError("Data-home recovery payload is invalid");
    }
    return { home, backupHome };
  }

  private dataHomeArguments(
    action: "inspect" | "recover" | "activate",
    explicitHome?: string,
  ): readonly string[] {
    return [
      "data-home",
      action,
      ...(explicitHome === undefined ? [] : ["--data-home", explicitHome]),
      "--json",
    ];
  }

  private parseJsonObject(output: string, message: string): Record<string, unknown> {
    const lines = output
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line !== "");
    for (let index = lines.length - 1; index >= 0; index -= 1) {
      const line = lines[index];
      if (line === undefined) continue;
      try {
        const candidate: unknown = JSON.parse(line);
        if (
          typeof candidate === "object"
          && candidate !== null
          && !Array.isArray(candidate)
        ) {
          return candidate as Record<string, unknown>;
        }
      } catch {
        // Inspect the next line for a structured command result.
      }
    }
    throw new LifecycleClientError(message);
  }

  private isStartupPhase(value: unknown): value is RuntimeStartupPhase {
    return value === "starting"
      || value === "core_ready"
      || value === "authority_starting"
      || value === "ready"
      || value === "stopping"
      || value === "failed";
  }

  private isDataHomeState(value: unknown): value is DataHomeState {
    return value === "fresh"
      || value === "ready"
      || value === "legacy"
      || value === "corrupt"
      || value === "permission";
  }

  private isLifecycleState(value: unknown): value is RuntimeStatus["state"] {
    return (
      value === "ready" ||
      value === "degraded" ||
      value === "starting" ||
      value === "stopping" ||
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
