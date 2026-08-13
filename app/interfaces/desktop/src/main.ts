import { app, BrowserWindow, Menu, nativeImage, Tray } from "electron";
import { randomUUID } from "node:crypto";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";

import {
  applicationMenuTemplate,
  backgroundMenuTemplate,
  normalizeApplicationMenuLocale,
} from "./application_menu.js";
import { DESKTOP_UI_INSTANCE_NAMESPACE, DesktopRoleController } from "./desktop_role_lifecycle.js";
import {
  lifecycleCommandExecutable,
  ManagedRuntimeLifecycleClient,
  ProcessLifecycleCommandRunner,
} from "./lifecycle_client.js";
import { loadAndValidateResourceManifest } from "./resources/resource_manifest.js";
import {
  createMainWindow,
  showStartupFailure,
  showStartupProgress,
} from "./windows/runtime_windows.js";
import {
  closeKeepsBackgroundServiceRunning,
  DEFAULT_MANAGEMENT_UI_URL,
} from "./windows/window_options.js";
import { SingleWindowRegistry } from "./windows/window_registry.js";

let roleController: DesktopRoleController | undefined;
let explicitExitRequested = false;
let exitInProgress = false;
const managementWindow = new SingleWindowRegistry<BrowserWindow>();
let backgroundTray: Tray | undefined;
let maintenanceTimer: NodeJS.Timeout | undefined;
let maintenanceRunning = false;
let runtimeUiAvailable = false;
let managementUiLoaded = false;

const uiUrl = process.env["ELFIENEST_UI_URL"] ?? DEFAULT_MANAGEMENT_UI_URL;

function trayIconPath(): string {
  const projectRoot = process.env["ELFIENEST_PROJECT_ROOT"];
  const packagedIcon = join(app.getAppPath(), "assets", "elfienest-tray-icon.png");
  const candidates = [
    packagedIcon,
    ...(projectRoot === undefined
      ? []
      : [join(projectRoot, "docs", "public", "assets", "elfienest-logo-mark-transparent.png")]),
    resolve(process.cwd(), "docs", "public", "assets", "elfienest-logo-mark-transparent.png"),
  ];
  return candidates.find((candidate) => existsSync(candidate)) ?? packagedIcon;
}

function ensureManagementWindow(): Readonly<{ window: BrowserWindow; created: boolean }> {
  const result = managementWindow.ensure(() => {
    const window = createMainWindow(process.platform);
    bindManagementWindow(window);
    showStartupProgress(window);
    return window;
  });
  if (result.created && runtimeUiAvailable) {
    void loadManagementUi(result.window);
  }
  return result;
}

async function loadManagementUi(window: BrowserWindow): Promise<void> {
  if (managementUiLoaded || !runtimeUiAvailable || window.isDestroyed()) return;
  managementUiLoaded = true;
  try {
    await window.loadURL(uiUrl);
  } catch (error: unknown) {
    managementUiLoaded = false;
    throw error;
  }
}

function showManagementWindow(): void {
  const { window } = ensureManagementWindow();
  if (process.platform === "darwin") {
    void app.dock?.show();
  }
  if (window.isMinimized()) {
    window.restore();
  }
  window.show();
  window.focus();
}

function hideManagementWindow(): void {
  managementWindow.current()?.hide();
  if (process.platform === "darwin") {
    app.dock?.hide();
  }
  void roleController?.closeWindow();
}

function bindManagementWindow(window: BrowserWindow): void {
  window.on("close", (event) => {
    if (!closeKeepsBackgroundServiceRunning(explicitExitRequested)) {
      return;
    }
    event.preventDefault();
    window.hide();
    if (process.platform === "darwin") {
      app.dock?.hide();
    }
    void roleController?.closeWindow();
  });
  window.on("closed", () => {
    managementWindow.clear(window);
    managementUiLoaded = false;
  });
}

function createBackgroundTray(locale: ReturnType<typeof normalizeApplicationMenuLocale>): void {
  const icon = nativeImage.createFromPath(trayIconPath()).resize({
    width: process.platform === "darwin" ? 18 : 22,
    height: process.platform === "darwin" ? 18 : 22,
  });
  if (process.platform === "darwin") {
    icon.setTemplateImage(true);
  }
  backgroundTray = new Tray(icon);
  backgroundTray.setToolTip("ElfieNest");
  backgroundTray.setContextMenu(
    Menu.buildFromTemplate(
      backgroundMenuTemplate(showManagementWindow, requestExplicitApplicationExit, locale),
    ),
  );
  if (process.platform !== "darwin") {
    backgroundTray.on("click", showManagementWindow);
  }
  backgroundTray.on("double-click", showManagementWindow);
}

function startOwnedRuntimeMaintenance(): void {
  maintenanceTimer = setInterval(() => {
    if (maintenanceRunning || roleController === undefined) {
      return;
    }
    maintenanceRunning = true;
    void roleController
      .maintainOwnedRuntime()
      .then((state) => {
        if (state.kind === "failed") {
          console.error("ElfieNest background Runtime recovery failed", state.reason);
        }
      })
      .finally(() => {
        maintenanceRunning = false;
      });
  }, 30_000);
}

async function startDesktop(): Promise<void> {
  if (app.isPackaged) {
    loadAndValidateResourceManifest(process.resourcesPath, app.getVersion());
  }
  const lifecycleCommand = lifecycleCommandExecutable(
    app.isPackaged,
    process.resourcesPath,
    process.platform,
  );
  roleController = new DesktopRoleController(
    new ManagedRuntimeLifecycleClient(
      `desktop-${randomUUID()}`,
      new ProcessLifecycleCommandRunner(lifecycleCommand),
    ),
  );
  const state = await roleController.start((phase) => {
    const window = managementWindow.current();
    if (window === undefined) return;
    if (phase === "core_ready") {
      runtimeUiAvailable = true;
      void loadManagementUi(window).catch((error: unknown) => {
        console.error("ElfieNest management UI failed to load", error);
      });
      return;
    }
    if (!runtimeUiAvailable) {
      showStartupProgress(window, phase);
    }
  });
  if (state.kind === "failed") {
    throw new Error(state.reason);
  }
  const window = managementWindow.current();
  if (window !== undefined) {
    runtimeUiAvailable = true;
    await loadManagementUi(window);
  }
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
    showManagementWindow();
  });

  void app
    .whenReady()
    .then(() => {
      const locale = normalizeApplicationMenuLocale(app.getLocale());
      Menu.setApplicationMenu(
        Menu.buildFromTemplate(
          applicationMenuTemplate(
            process.platform,
            showManagementWindow,
            hideManagementWindow,
            requestExplicitApplicationExit,
            locale,
          ),
        ),
      );
      createBackgroundTray(locale);
      showManagementWindow();
      return startDesktop().then(() => {
        startOwnedRuntimeMaintenance();
      });
    })
    .catch((error: unknown) => {
      const message = error instanceof Error ? error.message : "未知错误";
      console.error("ElfieNest Desktop 启动失败", message);
      const { window } = ensureManagementWindow();
      showStartupFailure(window, error);
      showManagementWindow();
    });
}

startDesktopUiRole();

app.on("before-quit", (event) => {
  if (!explicitExitRequested || exitInProgress) {
    return;
  }
  event.preventDefault();
  explicitExitRequested = false;
  exitInProgress = true;
  const cleanup = roleController?.exitApplication() ?? Promise.resolve();
  void cleanup
    .catch((error: unknown) => {
      const message = error instanceof Error ? error.message : String(error);
      console.error("ElfieNest Runtime cleanup during quit failed", message);
    })
    .finally(() => app.exit(0));
});

app.on("activate", () => {
  showManagementWindow();
});

app.on("window-all-closed", () => {
  if (backgroundTray === undefined && process.platform !== "darwin") {
    app.quit();
  }
});

export function requestExplicitApplicationExit(): void {
  if (exitInProgress) {
    return;
  }
  explicitExitRequested = true;
  if (maintenanceTimer !== undefined) {
    clearInterval(maintenanceTimer);
    maintenanceTimer = undefined;
  }
  managementWindow.current()?.hide();
  if (process.platform === "darwin") {
    app.dock?.hide();
  }
  backgroundTray?.destroy();
  backgroundTray = undefined;
  app.quit();
}
