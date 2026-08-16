import { BrowserWindow } from "electron";

import type { DataHomeInspection } from "../lifecycle_client.js";

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

export type StartupProgressPhase =
  | "starting"
  | "core_ready"
  | "authority_starting"
  | "world_ready"
  | "stopping"
  | "failed";

const startupCopy: Readonly<Record<StartupProgressPhase, string>> = {
  starting: "正在准备核心服务…",
  core_ready: "核心服务已就绪，正在打开监控页面…",
  authority_starting: "正在连接精灵巢…",
  world_ready: "精灵巢已连接…",
  stopping: "正在安全关闭后台服务…",
  failed: "后台服务启动失败",
};

export function showStartupProgress(
  window: BrowserWindow,
  phase: StartupProgressPhase = "starting",
): void {
  const detail = startupCopy[phase];
  const document = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>ElfieNest</title><style>html,body{height:100%;margin:0}body{display:grid;place-items:center;font:16px system-ui,sans-serif;color:#66584b;background:#fffaf1}main{text-align:center}h1{margin:0 0 12px;color:#3f352d;font-size:28px}p{margin:0;color:#887767}.pulse{width:34px;height:34px;margin:0 auto 22px;border:3px solid #ead6c0;border-top-color:#ae6038;border-radius:50%;animation:spin .9s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}</style><main><div aria-hidden="true" class="pulse"></div><h1>ElfieNest 正在启动</h1><p>${escapeHtml(detail)}</p></main></html>`;
  loadDocument(window, document);
}

export function showStartupFailure(window: BrowserWindow, error: unknown): void {
  const message = error instanceof Error ? error.message : "未知启动错误";
  const safeMessage = escapeHtml(message);
  const document = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>ElfieNest 启动失败</title><style>body{font:16px system-ui,sans-serif;background:#101418;color:#e8edf2;padding:48px}main{max-width:600px;margin:auto}h1{font-size:26px}pre{white-space:pre-wrap;background:#1b222a;border:1px solid #33404c;border-radius:8px;padding:16px;color:#ffb4ab}button{margin-top:20px;padding:10px 18px;border:0;border-radius:6px;background:#8bd5ca;color:#10201e;font-weight:600;cursor:pointer}</style><main><h1>ElfieNest 无法启动</h1><p>请根据下面的组件错误检查安装资源或本机权限。</p><pre>${safeMessage}</pre><button onclick="window.close()">关闭窗口</button></main></html>`;
  loadDocument(window, document);
}

export function showDataHomeRecovery(
  window: BrowserWindow,
  inspection: DataHomeInspection,
): void {
  const document = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>ElfieNest 数据恢复</title><style>html,body{height:100%;margin:0}body{font:16px system-ui,sans-serif;background:#101418;color:#e8edf2;padding:48px;box-sizing:border-box}main{max-width:680px;margin:8vh auto}h1{font-size:28px;margin:0 0 14px}p{line-height:1.6;color:#c4cdd6}.path{display:block;white-space:pre-wrap;overflow-wrap:anywhere;background:#1b222a;border:1px solid #33404c;border-radius:8px;padding:14px;color:#ffcfab}.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:26px}a{display:inline-block;padding:11px 18px;border-radius:7px;text-decoration:none;font-weight:600;background:#8bd5ca;color:#10201e}a.secondary{background:#29333d;color:#e8edf2}</style><main><h1>需要处理数据目录</h1><p>${escapeHtml(inspection.detail)}。应用暂时不会启动后台服务，也不会删除或覆盖你的旧数据。</p><p class="path">当前目录：${escapeHtml(inspection.home)}</p><p>推荐操作会先完整保留旧目录，再在原位置创建新的正式环境。旧账号、精灵和历史数据不会自动迁移。</p><div class="actions"><a href="elfienest://recover-data-home">备份旧数据并创建新环境（推荐）</a><a class="secondary" href="elfienest://choose-data-home">选择其他数据目录</a><a class="secondary" href="elfienest://open-data-home">打开数据目录</a><a class="secondary" href="elfienest://quit">退出</a></div></main></html>`;
  loadDocument(window, document);
}

export function showDataHomeRecoverySuccess(
  window: BrowserWindow,
  backupHome: string,
): void {
  const document = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>ElfieNest 数据恢复完成</title><style>html,body{height:100%;margin:0}body{display:grid;place-items:center;font:16px system-ui,sans-serif;background:#fffaf1;color:#66584b}main{max-width:680px;text-align:center;padding:32px}h1{color:#3f352d;font-size:28px}p{line-height:1.6}.path{display:block;text-align:left;white-space:pre-wrap;overflow-wrap:anywhere;background:#f2e5d5;border-radius:8px;padding:14px;color:#5d493b}a{display:inline-block;margin-top:18px;padding:11px 18px;border-radius:7px;text-decoration:none;font-weight:600;background:#ae6038;color:white}</style><main><h1>新环境已准备好</h1><p>旧数据没有被删除，已完整保留在：</p><p class="path">${escapeHtml(backupHome)}</p><a href="elfienest://continue-start">继续启动 ElfieNest</a></main></html>`;
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
