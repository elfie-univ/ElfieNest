import { app, BrowserWindow } from "electron";

import { RuntimeSupervisor, type HiddenRuntime } from "./supervisor.js";
import { resolveSupervisorConfig } from "./supervisor_config.js";

let supervisor: RuntimeSupervisor | undefined;
let stopping = false;
const hasSingleInstanceLock = app.requestSingleInstanceLock();

function showStartupFailure(error: unknown): void {
  const message = error instanceof Error ? error.message : "未知启动错误";
  const window = new BrowserWindow({
    width: 720,
    height: 520,
    resizable: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  const safeMessage = escapeHtml(message);
  const document = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>ElfieNest 启动失败</title><style>body{font:16px system-ui,sans-serif;background:#101418;color:#e8edf2;padding:48px}main{max-width:600px;margin:auto}h1{font-size:26px}pre{white-space:pre-wrap;background:#1b222a;border:1px solid #33404c;border-radius:8px;padding:16px;color:#ffb4ab}button{margin-top:20px;padding:10px 18px;border:0;border-radius:6px;background:#8bd5ca;color:#10201e;font-weight:600;cursor:pointer}</style><main><h1>ElfieNest 无法启动</h1><p>请根据下面的组件错误检查安装资源或本机权限。</p><pre>${safeMessage}</pre><button onclick="window.close()">退出</button></main></html>`;
  void window.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(document)}`);
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

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
    createMainWindow(process.env["ELFIENEST_UI_URL"] ?? "http://127.0.0.1:8000/");
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
