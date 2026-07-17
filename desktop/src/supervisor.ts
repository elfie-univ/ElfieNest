import { existsSync } from "node:fs";
import { get } from "node:http";
import { spawn, type SpawnOptions } from "node:child_process";
import { randomBytes } from "node:crypto";

import type { SupervisorConfig } from "./supervisor_config.js";

export type ComponentName = "ollama" | "core" | "godot";
export type SupervisorComponent = ComponentName | "supervisor";
export type ComponentState = "starting" | "ready" | "degraded" | "stopped";
export type SupervisorSnapshot = Readonly<Record<ComponentName, ComponentState>>;
export type SupervisorLifecycleState = "stopped" | "starting" | "ready" | "stopping";

export interface HiddenRuntime {
  load(url: string): Promise<void>;
  close(): void;
}

interface ManagedProcess {
  readonly exitCode: number | null;
  readonly killed: boolean;
  kill(signal?: NodeJS.Signals): boolean;
  onError(listener: (error: Error) => void): void;
  onExit(listener: () => void): void;
}

type ProcessSpawner = (
  name: ComponentName,
  command: string,
  args: readonly string[],
  options: Readonly<SpawnOptions>,
) => ManagedProcess;
type HealthChecker = (baseUrl: string, path: string) => Promise<void>;
type RuntimeReadyChecker = (healthUrl: string) => Promise<void>;
type ProcessStopper = (process: ManagedProcess) => Promise<void>;

export interface SupervisorDependencies {
  readonly spawnProcess?: ProcessSpawner;
  readonly waitForHttp?: HealthChecker;
  readonly waitForGodotReady?: RuntimeReadyChecker;
  readonly stopProcess?: ProcessStopper;
}

export class SupervisorError extends Error {
  readonly name = "SupervisorError";

  constructor(
    readonly component: SupervisorComponent,
    message: string,
  ) {
    super(message);
  }
}

const initialSnapshot: SupervisorSnapshot = {
  ollama: "stopped",
  core: "stopped",
  godot: "stopped",
};

export class RuntimeSupervisor {
  private readonly processes = new Map<ComponentName, ManagedProcess>();
  private snapshot: SupervisorSnapshot = initialSnapshot;
  private runtime: HiddenRuntime | undefined;
  private lifecycle: SupervisorLifecycleState = "stopped";
  private godotNonce: string | undefined;
  private readonly spawnProcess: ProcessSpawner;
  private readonly waitForHttp: HealthChecker;
  private readonly waitForGodotReady: RuntimeReadyChecker;
  private readonly stopProcess: ProcessStopper;

  constructor(
    private readonly config: SupervisorConfig,
    dependencies: SupervisorDependencies = {},
  ) {
    this.spawnProcess = dependencies.spawnProcess ?? spawnManagedProcess;
    this.waitForHttp = dependencies.waitForHttp ?? waitForHttp;
    this.waitForGodotReady = dependencies.waitForGodotReady ?? waitForGodotReady;
    this.stopProcess = dependencies.stopProcess ?? stopManagedProcess;
  }

  get status(): SupervisorSnapshot {
    return this.snapshot;
  }

  get lifecycleState(): SupervisorLifecycleState {
    return this.lifecycle;
  }

  async start(runtime: HiddenRuntime): Promise<SupervisorSnapshot> {
    if (this.lifecycle === "ready") {
      return this.snapshot;
    }
    if (this.lifecycle !== "stopped") {
      throw new SupervisorError("supervisor", "运行时监督器正在启动或停止");
    }

    this.lifecycle = "starting";
    this.runtime = runtime;
    this.godotNonce = randomBytes(32).toString("hex");
    let activeComponent: SupervisorComponent = "ollama";
    try {
      if (this.config.manageOllama) {
        activeComponent = "ollama";
        this.update("ollama", "starting");
        this.startProcess("ollama", this.config.ollamaExecutable, ["serve"]);
      }
      await this.waitForHttp(this.config.ollamaUrl, "/api/tags");
      this.update("ollama", "ready");

      activeComponent = "core";
      this.update("core", "starting");
      this.startProcess("core", this.config.coreExecutable, this.config.coreArgs);
      await this.waitForHttp(this.config.coreHealthUrl, "");
      this.update("core", "ready");

      activeComponent = "godot";
      this.update("godot", "starting");
      await runtime.load(appendNonce(this.config.godotUrl, this.godotNonce));
      await this.waitForGodotReady(this.config.coreHealthUrl);
      this.update("godot", "ready");
      this.lifecycle = "ready";
      return this.snapshot;
    } catch (error: unknown) {
      await this.stop();
      if (error instanceof SupervisorError) {
        throw error;
      }
      throw new SupervisorError(activeComponent, errorMessage(error));
    }
  }

  async stop(): Promise<void> {
    if (this.lifecycle === "stopping") {
      return;
    }
    this.lifecycle = "stopping";
    this.runtime?.close();
    this.runtime = undefined;
    this.godotNonce = undefined;
    const order: readonly ComponentName[] = ["godot", "core", "ollama"];
    for (const name of order) {
      const child = this.processes.get(name);
      if (child !== undefined) {
        await this.stopProcess(child);
        this.processes.delete(name);
      }
      this.update(name, "stopped");
    }
    this.lifecycle = "stopped";
  }

  private startProcess(
    name: ComponentName,
    command: string,
    args: readonly string[],
  ): void {
    if (command.includes("/") || command.includes("\\")) {
      if (!existsSync(command)) {
        throw new SupervisorError(name, `找不到内置运行时: ${command}`);
      }
    }
    const child = this.spawnProcess(name, command, args, {
      cwd: name === "core" ? this.config.coreWorkingDirectory : this.config.resourcesPath,
      env: {
        ...process.env,
        ELFIE_HOME: this.config.dataRoot,
        OLLAMA_MODELS: `${this.config.dataRoot}/models`,
        ELFIENEST_SUPERVISED: "1",
        ELFIENEST_GODOT_NONCE: this.godotNonce ?? "",
      },
      stdio: "ignore",
      windowsHide: true,
    });
    child.onError((error) => {
      this.update(name, "degraded");
      console.error(`ElfieNest ${name} 启动失败`, error.message);
    });
    child.onExit(() => {
      if (this.lifecycle === "starting" || this.lifecycle === "ready") {
        this.update(name, "degraded");
      }
    });
    this.processes.set(name, child);
  }

  private update(name: ComponentName, state: ComponentState): void {
    this.snapshot = { ...this.snapshot, [name]: state };
  }
}

function appendNonce(url: string, nonce: string): string {
  const target = new URL(url);
  target.searchParams.set("nonce", nonce);
  return target.toString();
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "未知启动错误";
}

function spawnManagedProcess(
  _name: ComponentName,
  command: string,
  args: readonly string[],
  options: Readonly<SpawnOptions>,
): ManagedProcess {
  const child = spawn(command, [...args], options);
  return {
    get exitCode(): number | null {
      return child.exitCode;
    },
    get killed(): boolean {
      return child.killed;
    },
    kill: (signal?: NodeJS.Signals): boolean => child.kill(signal),
    onError: (listener: (error: Error) => void): void => {
      child.once("error", listener);
    },
    onExit: (listener: () => void): void => {
      child.once("exit", listener);
    },
  };
}

function waitForHttp(baseUrl: string, path: string): Promise<void> {
  const target = new URL(path, baseUrl).toString();
  return new Promise((resolve, reject) => {
    let attempts = 0;
    let settled = false;
    let timer: NodeJS.Timeout | undefined;
    const finish = (error?: Error): void => {
      if (settled) {
        return;
      }
      settled = true;
      if (timer !== undefined) {
        clearTimeout(timer);
      }
      if (error === undefined) {
        resolve();
      } else {
        reject(error);
      }
    };
    const retry = (): void => {
      if (attempts >= 40) {
        finish(new Error(`健康检查超时: ${target}`));
        return;
      }
      timer = setTimeout(check, 250);
    };
    const check = (): void => {
      attempts += 1;
      const request = get(target, (response) => {
        response.resume();
        if (response.statusCode !== undefined && response.statusCode >= 200 && response.statusCode < 400) {
          finish();
          return;
        }
        retry();
      });
      request.once("error", retry);
    };
    check();
  });
}

function waitForGodotReady(healthUrl: string): Promise<void> {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    let settled = false;
    let timer: NodeJS.Timeout | undefined;
    const finish = (error?: Error): void => {
      if (settled) {
        return;
      }
      settled = true;
      if (timer !== undefined) {
        clearTimeout(timer);
      }
      if (error === undefined) {
        resolve();
      } else {
        reject(error);
      }
    };
    const retry = (): void => {
      if (attempts >= 40) {
        finish(new Error(`Godot Runtime 握手超时: ${healthUrl}`));
        return;
      }
      timer = setTimeout(check, 250);
    };
    const check = (): void => {
      attempts += 1;
      const request = get(healthUrl, (response) => {
        let body = "";
        response.setEncoding("utf8");
        response.on("data", (chunk: string) => {
          body += chunk;
        });
        response.once("end", () => {
          if (response.statusCode !== 200) {
            retry();
            return;
          }
          try {
            const payload: unknown = JSON.parse(body);
            if (
              typeof payload === "object" &&
              payload !== null &&
              "godot_runtime_ready" in payload &&
              payload.godot_runtime_ready === true
            ) {
              finish();
              return;
            }
          } catch (error: unknown) {
            if (!(error instanceof SyntaxError)) {
              throw error;
            }
          }
          retry();
        });
      });
      request.once("error", retry);
    };
    check();
  });
}

function stopManagedProcess(child: ManagedProcess): Promise<void> {
  return new Promise((resolve) => {
    if (child.exitCode !== null || child.killed) {
      resolve();
      return;
    }
    let settled = false;
    let timer: NodeJS.Timeout | undefined;
    const finish = (): void => {
      if (settled) {
        return;
      }
      settled = true;
      if (timer !== undefined) {
        clearTimeout(timer);
      }
      resolve();
    };
    timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish();
    }, 3000);
    child.onExit(finish);
    child.kill("SIGTERM");
  });
}
