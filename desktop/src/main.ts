import { app, BrowserWindow } from "electron";

import { resolveSupervisorConfig } from "./platform/supervisor_config.js";
import { loadAndValidateResourceManifest } from "./resources/resource_manifest.js";
import { RuntimeSupervisor } from "./supervisor/supervisor.js";
import {
  createHiddenGodotRuntime,
  createMainWindow,
  showStartupFailure,
} from "./windows/runtime_windows.js";

let supervisor: RuntimeSupervisor | undefined;
let stopping = false;
const hasSingleInstanceLock = app.requestSingleInstanceLock();

async function startDesktop(): Promise<void> {
  const config = resolveSupervisorConfig(
    process.env,
    process.resourcesPath,
    app.getAppPath(),
    process.platform,
    app.getPath("userData"),
  );
  if (app.isPackaged) {
    loadAndValidateResourceManifest(config.resourcesPath, app.getVersion());
  }
  supervisor = new RuntimeSupervisor(config);
  await supervisor.start(createHiddenGodotRuntime());
  createMainWindow(config.uiUrl);
}

if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    const window = BrowserWindow.getAllWindows()[0];
    if (window !== undefined) {
      if (window.isMinimized()) {
        window.restore();
      }
      window.focus();
    }
  });

  void app.whenReady().then(() => startDesktop()).catch((error: unknown) => {
    const message = error instanceof Error ? error.message : "未知错误";
    console.error("ElfieNest Desktop 启动失败", message);
    showStartupFailure(error);
  });
}

app.on("before-quit", (event) => {
  if (stopping || supervisor === undefined) {
    return;
  }
  event.preventDefault();
  stopping = true;
  void supervisor.stop().then(() => app.exit(0));
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0 && supervisor?.status.core === "ready") {
    createMainWindow(
      process.env["ELFIENEST_UI_URL"] ?? "http://127.0.0.1:8000/login",
    );
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
