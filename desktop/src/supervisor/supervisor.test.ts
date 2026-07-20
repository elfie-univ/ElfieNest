import { strict as assert } from "node:assert";
import test from "node:test";

import {
  RuntimeSupervisor,
  SupervisorError,
  type HiddenRuntime,
} from "./supervisor.js";
import type { SupervisorConfig } from "../platform/supervisor_config.js";

class FakeProcess {
  exitCode: number | null = null;
  killed = false;
  private errorListener: ((error: Error) => void) | undefined;
  private exitListener: (() => void) | undefined;

  constructor(private readonly onKill: () => void) {}

  kill(): boolean {
    this.killed = true;
    this.exitCode = 0;
    this.onKill();
    this.exitListener?.();
    return true;
  }

  onError(listener: (error: Error) => void): void {
    this.errorListener = listener;
  }

  onExit(listener: () => void): void {
    this.exitListener = listener;
  }

  fail(message: string): void {
    this.errorListener?.(new Error(message));
  }
}

function createConfig(): SupervisorConfig {
  return {
    dataRoot: "/tmp/elfienest-test",
    uiUrl: "http://127.0.0.1:8000/",
    godotUrl: "http://127.0.0.1:8000/static/godot.html",
    ollamaUrl: "http://127.0.0.1:11434",
    coreHealthUrl: "http://127.0.0.1:8000/api/health",
    ollamaExecutable: "ollama",
    coreExecutable: "python",
    coreArgs: ["serve.py"],
    resourcesPath: "/tmp/elfienest-resources",
    coreWorkingDirectory: "/tmp/elfienest-core",
    manageOllama: true,
  };
}

function createRuntime(events: string[]): HiddenRuntime {
  return {
    load: async (): Promise<void> => {
      events.push("godot:load");
    },
    close: (): void => {
      events.push("godot:close");
    },
  };
}

test("supervisor starts components once and returns the same ready snapshot", async () => {
  // Given
  const spawned: string[] = [];
  const healthChecks: string[] = [];
  const events: string[] = [];
  const supervisor = new RuntimeSupervisor(createConfig(), {
    spawnProcess: (name) => {
      spawned.push(name);
      return new FakeProcess(() => events.push(`${name}:stop`));
    },
    waitForHttp: async (baseUrl, path) => {
      healthChecks.push(`${baseUrl}${path}`);
    },
    waitForGodotReady: async (): Promise<void> => undefined,
  });

  // When
  const first = await supervisor.start(createRuntime(events));
  const second = await supervisor.start(createRuntime(events));

  // Then
  assert.deepEqual(spawned, ["ollama", "core"]);
  assert.deepEqual(healthChecks, [
    "http://127.0.0.1:11434/api/tags",
    "http://127.0.0.1:8000/api/health",
  ]);
  assert.deepEqual(first, second);
  assert.equal(supervisor.lifecycleState, "ready");
  assert.deepEqual(events, ["godot:load"]);
});

test("supervisor passes independent runtime and camera credentials", async () => {
  // Given
  let loadedUrl = "";
  const supervisor = new RuntimeSupervisor(createConfig(), {
    spawnProcess: () => new FakeProcess(() => undefined),
    waitForHttp: async (): Promise<void> => undefined,
    waitForGodotReady: async (): Promise<void> => undefined,
  });

  // When
  await supervisor.start({
    load: async (url: string): Promise<void> => {
      loadedUrl = url;
    },
    close: (): void => undefined,
  });

  // Then
  const parsed = new URL(loadedUrl);
  const nonce = parsed.searchParams.get("nonce");
  const cameraToken = parsed.searchParams.get("camera_token");
  assert.ok(nonce);
  assert.ok(cameraToken);
  assert.notEqual(nonce, cameraToken);
  await supervisor.stop();
});

test("supervisor attributes startup failure and cleans every started process", async () => {
  // Given
  const events: string[] = [];
  const supervisor = new RuntimeSupervisor(createConfig(), {
    spawnProcess: (name) => new FakeProcess(() => events.push(`${name}:stop`)),
    waitForHttp: async (_baseUrl, path) => {
      if (path === "") {
        throw new Error("core health unavailable");
      }
    },
  });

  // When / Then
  await assert.rejects(
    supervisor.start(createRuntime(events)),
    (error: unknown) =>
      error instanceof SupervisorError &&
      error.message === "core health unavailable" &&
      error.component === "core",
  );
  assert.equal(supervisor.lifecycleState, "stopped");
  assert.deepEqual(events, ["godot:close", "core:stop", "ollama:stop"]);
  assert.deepEqual(supervisor.status, {
    ollama: "stopped",
    core: "stopped",
    godot: "stopped",
  });
});

test("supervisor stop releases the hidden runtime before managed processes", async () => {
  // Given
  const events: string[] = [];
  const supervisor = new RuntimeSupervisor(createConfig(), {
    spawnProcess: (name) => new FakeProcess(() => events.push(`${name}:stop`)),
    waitForHttp: async (): Promise<void> => undefined,
    waitForGodotReady: async (): Promise<void> => undefined,
  });
  await supervisor.start(createRuntime(events));

  // When
  await supervisor.stop();

  // Then
  assert.deepEqual(events, ["godot:load", "godot:close", "core:stop", "ollama:stop"]);
  assert.equal(supervisor.lifecycleState, "stopped");
});

test("supervisor does not mark Godot ready before runtime handshake", async () => {
  // Given
  const events: string[] = [];
  const supervisor = new RuntimeSupervisor(createConfig(), {
    spawnProcess: (name) => new FakeProcess(() => events.push(`${name}:stop`)),
    waitForHttp: async (): Promise<void> => undefined,
    waitForGodotReady: async (): Promise<void> => {
      throw new Error("runtime handshake pending");
    },
  });

  // When / Then
  await assert.rejects(
    supervisor.start(createRuntime(events)),
    (error: unknown) =>
      error instanceof SupervisorError &&
      error.message === "runtime handshake pending" &&
      error.component === "godot",
  );
  assert.equal(supervisor.status.godot, "stopped");
});
