import { BrowserWindow } from "electron";

import type { HiddenRuntime } from "../supervisor/supervisor.js";

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function showStartupFailure(error: unknown): void {
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

export function createMainWindow(uiUrl: string): BrowserWindow {
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

export function createHiddenGodotRuntime(): HiddenRuntime {
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
