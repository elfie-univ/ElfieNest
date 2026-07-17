import { app, BrowserWindow } from "electron";

import { RuntimeSupervisor, type HiddenRuntime } from "./supervisor.js";
import { resolveSupervisorConfig } from "./supervisor_config.js";

let supervisor: RuntimeSupervisor | undefined;
let stopping = false;
const hasSingleInstanceLock = app.requestSingleInstanceLock();

function createMainWindow(uiUrl: string): BrowserWindow {
  const window = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1024,
    minHeight: 720,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  void window.loadURL(uiUrl);
  return window;
}

function createHiddenGodotRuntime(): HiddenRuntime {
  const window = new BrowserWindow({
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false,
    },
  });
  return {
    load: (url: string): Promise<void> => window.loadURL(url),
    close: (): void => {
      if (!window.isDestroyed()) {
        window.close();
      }
    },
  };
}

async function startDesktop(): Promise<void> {
  const config = resolveSupervisorConfig(
    process.env,
    process.resourcesPath,
    app.getAppPath(),
    process.platform,
    app.getPath("userData"),
  );
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
    app.quit();
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
    createMainWindow(process.env["ELFIENEST_UI_URL"] ?? "http://127.0.0.1:8000/");
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
