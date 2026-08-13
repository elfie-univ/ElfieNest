import { BrowserWindow } from "electron";

import {
  MACOS_CONTENT_INSET_CSS,
  mainWindowOptions,
} from "./window_options.js";

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function loadDocument(window: BrowserWindow, document: string): void {
  void window.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(document)}`);
}

export function showStartupProgress(window: BrowserWindow): void {
  const document = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>ElfieNest</title><style>html,body{height:100%;margin:0}body{display:grid;place-items:center;font:16px system-ui,sans-serif;color:#66584b;background:#fffaf1}main{text-align:center}h1{margin:0 0 12px;color:#3f352d;font-size:28px}p{margin:0;color:#887767}.pulse{width:34px;height:34px;margin:0 auto 22px;border:3px solid #ead6c0;border-top-color:#ae6038;border-radius:50%;animation:spin .9s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}</style><main><div class="pulse"></div><h1>ElfieNest 正在启动</h1><p>正在准备后台服务与精灵巢…</p></main></html>`;
  loadDocument(window, document);
}

export function showStartupFailure(window: BrowserWindow, error: unknown): void {
  const message = error instanceof Error ? error.message : "未知启动错误";
  const safeMessage = escapeHtml(message);
  const document = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>ElfieNest 启动失败</title><style>body{font:16px system-ui,sans-serif;background:#101418;color:#e8edf2;padding:48px}main{max-width:600px;margin:auto}h1{font-size:26px}pre{white-space:pre-wrap;background:#1b222a;border:1px solid #33404c;border-radius:8px;padding:16px;color:#ffb4ab}button{margin-top:20px;padding:10px 18px;border:0;border-radius:6px;background:#8bd5ca;color:#10201e;font-weight:600;cursor:pointer}</style><main><h1>ElfieNest 无法启动</h1><p>请根据下面的组件错误检查安装资源或本机权限。</p><pre>${safeMessage}</pre><button onclick="window.close()">关闭窗口</button></main></html>`;
  loadDocument(window, document);
}

export function createMainWindow(platform: NodeJS.Platform): BrowserWindow {
  const window = new BrowserWindow(mainWindowOptions(platform));
  if (platform === "darwin") {
    window.webContents.on("did-finish-load", () => {
      void window.webContents.insertCSS(MACOS_CONTENT_INSET_CSS);
    });
  }
  return window;
}
