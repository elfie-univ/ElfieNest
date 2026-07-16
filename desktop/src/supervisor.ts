import { existsSync } from "node:fs";
import { get } from "node:http";
import { spawn, type ChildProcess } from "node:child_process";

import type { SupervisorConfig } from "./supervisor_config";

export type ComponentName = "ollama" | "core" | "godot";
export type ComponentState = "starting" | "ready" | "degraded" | "stopped";
export type SupervisorSnapshot = Readonly<Record<ComponentName, ComponentState>>;

export interface HiddenRuntime {
  load(url: string): Promise<void>;
  close(): void;
}

export class SupervisorError extends Error {
  readonly component: ComponentName;

  constructor(component: ComponentName, message: string) {
    super(message);
    this.name = "SupervisorError";
    this.component = component;
  }
}

const initialSnapshot: SupervisorSnapshot = {
  ollama: "stopped",
  core: "stopped",
  godot: "stopped",
};

export class RuntimeSupervisor {
  private readonly processes = new Map<ComponentName, ChildProcess>();
  private snapshot: SupervisorSnapshot = initialSnapshot;
  private runtime: HiddenRuntime | undefined;

  constructor(private readonly config: SupervisorConfig) {}

  get status(): SupervisorSnapshot {
    return this.snapshot;
  }

  async start(runtime: HiddenRuntime): Promise<SupervisorSnapshot> {
    this.runtime = runtime;
    try {
      if (this.config.manageOllama) {
        this.update("ollama", "starting");
        this.spawnProcess("ollama", this.config.ollamaExecutable, ["serve"]);
      }
      await waitForHttp(this.config.ollamaUrl, "/api/tags");
      this.update("ollama", "ready");

      this.update("core", "starting");
      this.spawnProcess("core", this.config.coreExecutable, this.config.coreArgs);
      await waitForHttp(this.config.coreHealthUrl, "");
      this.update("core", "ready");

      this.update("godot", "starting");
      await runtime.load(this.config.godotUrl);
      this.update("godot", "ready");
      return this.snapshot;
    } catch (error: unknown) {
      await this.stop();
      if (error instanceof SupervisorError) {
        throw error;
      }
      throw new SupervisorError("core", errorMessage(error));
    }
  }

  async stop(): Promise<void> {
    this.runtime?.close();
    this.runtime = undefined;
    const order: readonly ComponentName[] = ["core", "ollama"];
    for (const name of order) {
      const child = this.processes.get(name);
      if (child !== undefined) {
        await stopProcess(child);
        this.processes.delete(name);
      }
      this.update(name, "stopped");
    }
    this.update("godot", "stopped");
  }

  private spawnProcess(name: ComponentName, command: string, args: readonly string[]): void {
    if (command.includes("/") || command.includes("\\")) {
      if (!existsSync(command)) {
        throw new SupervisorError(name, `找不到内置运行时: ${command}`);
      }
    }
    const child = spawn(command, [...args], {
      cwd: name === "core" ? this.config.coreWorkingDirectory : this.config.resourcesPath,
      env: {
        ...process.env,
        ELFIE_HOME: this.config.dataRoot,
        OLLAMA_MODELS: `${this.config.dataRoot}/models`,
        ELFIENEST_SUPERVISED: "1",
      },
      stdio: "ignore",
      windowsHide: true,
    });
    child.once("error", (error: Error) => {
      this.update(name, "degraded");
      console.error(`ElfieNest ${name} 启动失败`, error.message);
    });
    this.processes.set(name, child);
  }

  private update(name: ComponentName, state: ComponentState): void {
    this.snapshot = { ...this.snapshot, [name]: state };
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "未知启动错误";
}

function waitForHttp(baseUrl: string, path: string): Promise<void> {
  const target = new URL(path, baseUrl).toString();
  return new Promise((resolve, reject) => {
    let attempts = 0;
    let timer: NodeJS.Timeout | undefined;
    const check = (): void => {
      attempts += 1;
      const request = get(target, (response) => {
        response.resume();
        if (response.statusCode !== undefined && response.statusCode >= 200 && response.statusCode < 400) {
          resolve();
          return;
        }
        retry();
      });
      request.once("error", retry);
    };
    const retry = (): void => {
      if (attempts >= 40) {
        reject(new Error(`健康检查超时: ${target}`));
        return;
      }
      timer = setTimeout(check, 250);
    };
    check();
    void timer;
  });
}

function stopProcess(child: ChildProcess): Promise<void> {
  return new Promise((resolve) => {
    if (child.exitCode !== null || child.killed) {
      resolve();
      return;
    }
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      resolve();
    }, 3000);
    child.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
    child.kill("SIGTERM");
  });
}
