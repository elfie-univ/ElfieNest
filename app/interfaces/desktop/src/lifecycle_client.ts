import { execFile, spawn } from "node:child_process";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { promisify } from "node:util";

import type {
  LifecycleClient,
  RuntimeAttachment,
} from "./desktop_role_lifecycle.js";

type RuntimeStatus = Readonly<{
  readonly state: "offline" | "core_ready" | "world_ready";
  readonly phase: string;
  readonly generation: number;
  readonly instanceId: string | null;
  readonly ownerLease: string | null;
  readonly startupOwnerId: string | null;
  readonly httpUrl: string | null;
  readonly failures: readonly RuntimeFailure[];
}>;

type RuntimeFailure = Readonly<{
  readonly code: string;
  readonly detail: string;
}>;

export type RuntimeHealthTarget = Readonly<{
  readonly httpUrl: string;
  readonly instanceId: string;
  readonly generation: number;
}>;

export type RuntimeHealthProbe = (
  target: RuntimeHealthTarget,
) => Promise<boolean>;

export type DataHomeState = "fresh" | "partial" | "ready" | "legacy" | "corrupt" | "permission";

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
  | "world_ready"
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
const STARTUP_ATTACH_TIMEOUT_MS = 30_000;
const STARTUP_ATTACH_POLL_MS = 250;
const RUNTIME_HEALTH_TIMEOUT_MS = 2_000;

export function runtimeHealthMatches(
  payload: unknown,
  target: RuntimeHealthTarget,
): boolean {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return false;
  }
  // Desktop only verifies that the same Core generation is still alive here.
  // RuntimeWorldWorker remains the sole owner of Godot/World recovery.
  return Reflect.get(payload, "status") === "ok"
    && Reflect.get(payload, "engine_ready") === true
    && Reflect.get(payload, "instance_id") === target.instanceId
    && Reflect.get(payload, "generation") === target.generation;
}

export async function probeRuntimeHealth(
  target: RuntimeHealthTarget,
): Promise<boolean> {
  try {
    const response = await fetch(new URL("/api/health", target.httpUrl), {
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(RUNTIME_HEALTH_TIMEOUT_MS),
    });
    if (!response.ok) return false;
    return runtimeHealthMatches(await response.json(), target);
  } catch {
    return false;
  }
}

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
  private selectedDataHome: string | undefined;
  private ownedRuntimeHealthTarget: RuntimeHealthTarget | undefined;

  constructor(
    private readonly ownerLease: string,
    private readonly commandRunner: LifecycleCommandRunner = new ProcessLifecycleCommandRunner(),
    private readonly runtimeHealthProbe: RuntimeHealthProbe = probeRuntimeHealth,
  ) {}

  async inspectDataHome(explicitHome?: string): Promise<DataHomeInspection> {
    const inspection = this.parseDataHomeInspection(
      await this.commandRunner.run(
        this.controllerDataHomeArguments("inspect", explicitHome),
      ),
    );
    this.selectedDataHome = inspection.home;
    return inspection;
  }

  async recoverDataHome(explicitHome?: string): Promise<DataHomeRecoveryResult> {
    return this.parseDataHomeRecovery(
      await this.commandRunner.run(
        this.controllerDataHomeArguments("recover", explicitHome),
      ),
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
        return {
          kind: "attached",
          generation: initial.generation,
          dataHome: this.requireSelectedDataHome(),
          ...(initial.httpUrl === null ? {} : { httpUrl: initial.httpUrl }),
        };
      }
      if (initial.phase === "core_starting") {
        return this.waitForStartup(initial);
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
        return this.ownedAttachment(started);
      }
      return this.failure(
        this.firstFailureDetail(started) ?? "Runtime did not grant the desktop owner lease",
      );
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
      const healthTarget = this.ownedRuntimeHealthTarget;
      if (
        healthTarget !== undefined
        && await this.runtimeHealthProbeSafely(healthTarget)
      ) {
        return this.ownedAttachmentFromHealthTarget(healthTarget);
      }
      const current = await this.status();
      if (this.isReady(current) && current.ownerLease === ownerLease) {
        return this.ownedAttachment(current);
      }
      if (current.phase === "core_starting" && current.ownerLease === ownerLease) {
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

  private async waitForStartup(initial: RuntimeStatus): Promise<RuntimeAttachment> {
    const deadline = Date.now() + STARTUP_ATTACH_TIMEOUT_MS;
    let current = initial;
    while (current.phase === "core_starting" && Date.now() < deadline) {
      await new Promise<void>((resolve) => {
        setTimeout(resolve, STARTUP_ATTACH_POLL_MS);
      });
      current = await this.status();
    }
    if (this.isReady(current) && current.ownerLease !== null) {
      return {
        kind: "attached",
        generation: current.generation,
        dataHome: this.requireSelectedDataHome(),
        ...(current.httpUrl === null ? {} : { httpUrl: current.httpUrl }),
      };
    }
    if (current.phase === "core_starting") {
      return this.failure("Runtime startup did not become ready before timeout");
    }
    return this.failure(
      current.phase === "failed"
        ? this.firstFailureDetail(current) ?? "Runtime startup failed while Desktop was waiting"
        : "Runtime did not become ready while Desktop was waiting",
    );
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
    const tier = Reflect.get(payload, "tier");
    const phase = Reflect.get(payload, "phase");
    const generation = Reflect.get(payload, "generation");
    const ownerLease = Reflect.get(payload, "owner_lease");
    const startupOwnerId = Reflect.get(payload, "startup_owner_id");
    const rawInstanceId = Reflect.get(payload, "instance_id");
    const failures = this.parseFailures(payload);
    if (
      !this.isLifecycleState(tier ?? state) ||
      typeof phase !== "string" ||
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
    if (
      rawInstanceId !== undefined
      && rawInstanceId !== null
      && (typeof rawInstanceId !== "string" || rawInstanceId === "")
    ) {
      throw new LifecycleClientError("Lifecycle instance identity is invalid");
    }
    const instanceId = typeof rawInstanceId === "string" ? rawInstanceId : null;
    if (ownerLease === null) {
      return {
        state: (tier ?? state) as RuntimeStatus["state"],
        phase,
        generation,
        instanceId,
        ownerLease: null,
        startupOwnerId: typeof startupOwnerId === "string" ? startupOwnerId : null,
        httpUrl: this.parseHttpUrl(payload),
        failures,
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
      state: (tier ?? state) as RuntimeStatus["state"],
      phase,
      generation,
      instanceId,
      ownerLease: ownerLease.owner_id,
      startupOwnerId: typeof startupOwnerId === "string" ? startupOwnerId : null,
      httpUrl: this.parseHttpUrl(payload),
      failures,
    };
  }

  private parseFailures(payload: object): readonly RuntimeFailure[] {
    const rawFailures = Reflect.get(payload, "failures");
    if (rawFailures === undefined) return [];
    if (!Array.isArray(rawFailures)) {
      throw new LifecycleClientError("Lifecycle failure list is invalid");
    }
    const failures: RuntimeFailure[] = [];
    for (const rawFailure of rawFailures) {
      if (
        typeof rawFailure !== "object"
        || rawFailure === null
        || Array.isArray(rawFailure)
        || typeof Reflect.get(rawFailure, "code") !== "string"
        || typeof Reflect.get(rawFailure, "detail") !== "string"
      ) {
        throw new LifecycleClientError("Lifecycle failure item is invalid");
      }
      failures.push({
        code: Reflect.get(rawFailure, "code") as string,
        detail: Reflect.get(rawFailure, "detail") as string,
      });
    }
    return failures;
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

  private controllerDataHomeArguments(
    action: "inspect" | "recover",
    explicitHome?: string,
  ): readonly string[] {
    return [
      "--__controller-action",
      action === "inspect" ? "inspect-data-home" : "recover-data-home",
      ...(explicitHome === undefined
        ? []
        : ["--__controller-data-home", explicitHome]),
    ];
  }

  private requireSelectedDataHome(): string {
    if (this.selectedDataHome === undefined) {
      throw new LifecycleClientError("Installed data root was not resolved");
    }
    return this.selectedDataHome;
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
      || value === "world_ready"
      || value === "stopping"
      || value === "failed";
  }

  private isDataHomeState(value: unknown): value is DataHomeState {
    return value === "fresh"
      || value === "partial"
      || value === "ready"
      || value === "legacy"
      || value === "corrupt"
      || value === "permission";
  }

  private isLifecycleState(value: unknown): value is RuntimeStatus["state"] {
    return (
      value === "offline" ||
      value === "core_ready" ||
      value === "world_ready"
    );
  }

  private isReady(status: RuntimeStatus): boolean {
    return status.state === "core_ready" || status.state === "world_ready";
  }

  private ownedAttachment(status: RuntimeStatus): RuntimeAttachment {
    const attachment: RuntimeAttachment = {
      kind: "owned",
      generation: status.generation,
      ownerLease: this.ownerLease,
      dataHome: this.requireSelectedDataHome(),
      ...(status.httpUrl === null ? {} : { httpUrl: status.httpUrl }),
    };
    this.ownedRuntimeHealthTarget = (
      status.httpUrl !== null
      && status.instanceId !== null
      && status.instanceId !== "uninitialized"
      && status.instanceId !== "unavailable"
    )
      ? {
        httpUrl: status.httpUrl,
        instanceId: status.instanceId,
        generation: status.generation,
      }
      : undefined;
    return attachment;
  }

  private ownedAttachmentFromHealthTarget(
    target: RuntimeHealthTarget,
  ): RuntimeAttachment {
    return {
      kind: "owned",
      generation: target.generation,
      ownerLease: this.ownerLease,
      dataHome: this.requireSelectedDataHome(),
      httpUrl: target.httpUrl,
    };
  }

  private async runtimeHealthProbeSafely(
    target: RuntimeHealthTarget,
  ): Promise<boolean> {
    try {
      return await this.runtimeHealthProbe(target);
    } catch {
      return false;
    }
  }

  private parseHttpUrl(payload: object): string | null {
    const endpoints = Reflect.get(payload, "endpoints");
    if (!Array.isArray(endpoints)) return null;
    for (const endpoint of endpoints) {
      if (typeof endpoint !== "object" || endpoint === null || Array.isArray(endpoint)) {
        continue;
      }
      const name = Reflect.get(endpoint, "name");
      const scheme = Reflect.get(endpoint, "scheme");
      const host = Reflect.get(endpoint, "host");
      const port = Reflect.get(endpoint, "port");
      if (
        name !== "http"
        || scheme !== "http"
        || typeof host !== "string"
        || !this.isLoopbackHost(host)
        || typeof port !== "number"
        || !Number.isInteger(port)
        || port < 1
        || port > 65535
      ) {
        continue;
      }
      return `http://${host}:${port}/`;
    }
    return null;
  }

  private isLoopbackHost(host: string): boolean {
    return host === "127.0.0.1" || host === "localhost" || host === "::1";
  }

  private failure(reason: string): RuntimeAttachment {
    return { kind: "failed", reason, recoverable: true };
  }

  private firstFailureDetail(status: RuntimeStatus): string | undefined {
    return status.failures.find((failure) => failure.detail.trim() !== "")?.detail;
  }

  private errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : "Lifecycle command failed";
  }
}
