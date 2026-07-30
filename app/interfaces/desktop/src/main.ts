import { app, BrowserWindow, Menu } from "electron";
import { randomUUID } from "node:crypto";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import {
  applicationMenuTemplate,
  normalizeApplicationMenuLocale,
} from "./application_menu.js";
import { DESKTOP_UI_INSTANCE_NAMESPACE, DesktopRoleController } from "./desktop_role_lifecycle.js";
import { ManagedRuntimeLifecycleClient } from "./lifecycle_client.js";
import { resolveElectronRole } from "./role_dispatch.js";
import { createMainWindow, showStartupFailure } from "./windows/runtime_windows.js";

let roleController: DesktopRoleController | undefined;
let explicitExitRequested = false;

async function startDesktop(): Promise<void> {
  const uiUrl = process.env["ELFIENEST_UI_URL"] ?? "http://127.0.0.1:8000/login";
  const lifecycleCommand = process.env["ELFIENEST_LIFECYCLE_COMMAND"] ?? "elfienest";
  roleController = new DesktopRoleController(
    new ManagedRuntimeLifecycleClient(lifecycleCommand, `desktop-${randomUUID()}`),
  );
  const state = await roleController.start();
  if (state.kind === "failed") {
    throw new Error(state.reason);
  }
  createMainWindow(uiUrl);
}

function startDesktopUiRole(): void {
  app.setPath(
    "userData",
    join(app.getPath("userData"), DESKTOP_UI_INSTANCE_NAMESPACE),
  );
  const hasSingleInstanceLock = app.requestSingleInstanceLock();
  if (!hasSingleInstanceLock) {
    app.quit();
    return;
  }
  app.on("second-instance", () => {
    const window = BrowserWindow.getAllWindows()[0];
    if (window !== undefined) {
      if (window.isMinimized()) {
        window.restore();
      }
      window.focus();
    }
  });

  void app
    .whenReady()
    .then(() => {
      Menu.setApplicationMenu(
        Menu.buildFromTemplate(
          applicationMenuTemplate(
            process.platform,
            requestExplicitApplicationExit,
            normalizeApplicationMenuLocale(app.getLocale()),
          ),
        ),
      );
      return startDesktop();
    })
    .catch((error: unknown) => {
      const message = error instanceof Error ? error.message : "未知错误";
      console.error("ElfieNest Desktop 启动失败", message);
      showStartupFailure(error);
    });
}

function startGodotAuthorityRole(): void {
  const projectRoot =
    process.env["ELFIENEST_PROJECT_ROOT"] ?? join(process.cwd(), "..", "..", "..");
  const entry = app.isPackaged
    ? join(app.getAppPath(), "godot_runtime", "electron", "authority_main.mjs")
    : join(projectRoot, "godot_runtime", "electron", "authority_main.mjs");
  void import(pathToFileURL(entry).href);
}

if (resolveElectronRole(process.argv) === "godot-authority") {
  startGodotAuthorityRole();
} else {
  startDesktopUiRole();

  app.on("before-quit", (event) => {
    if (!explicitExitRequested || roleController === undefined) {
      return;
    }
    event.preventDefault();
    explicitExitRequested = false;
    void roleController.exitApplication().then(() => app.exit(0));
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0 && roleController !== undefined) {
      createMainWindow(process.env["ELFIENEST_UI_URL"] ?? "http://127.0.0.1:8000/login");
    }
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });
}

export function requestExplicitApplicationExit(): void {
  explicitExitRequested = true;
  app.quit();
}
