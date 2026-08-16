import {
  app,
  BrowserWindow,
  dialog,
  Menu,
  nativeImage,
  shell,
  Tray,
} from "electron";
import { randomUUID } from "node:crypto";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";

import {
  applicationMenuTemplate,
  backgroundMenuTemplate,
  normalizeApplicationMenuLocale,
} from "./application_menu.js";
import {
  DesktopRoleController,
  type DesktopRoleState,
} from "./desktop_role_lifecycle.js";
import {
  controllerHomeForAppData,
  startControllerIpcServer,
  type ControllerIpcServer,
} from "./controller_ipc.js";
import {
  lifecycleCommandExecutable,
  ManagedRuntimeLifecycleClient,
  ProcessLifecycleCommandRunner,
} from "./lifecycle_client.js";
import { loadAndValidateResourceManifest } from "./resources/resource_manifest.js";
import {
  createMainWindow,
  showDataHomeRecovery,
  showDataHomeRecoverySuccess,
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
let maintenanceStarted = false;
let runtimeUiAvailable = false;
let managementUiLoaded = false;
let recoveryActionHandler: ((action: RecoveryAction) => void) | undefined;
let recoveryActionRunning = false;
let controllerIpcServer: ControllerIpcServer | undefined;
const controllerOnly = process.argv.includes("--background");
let controllerEnsurePending = false;
let controllerStartPromise: Promise<DesktopRoleState> | undefined;

type RecoveryAction =
  | "recover-data-home"
  | "choose-data-home"
  | "open-data-home"
  | "continue-start"
  | "quit";

const uiUrl = process.env["ELFIENEST_UI_URL"] ?? DEFAULT_MANAGEMENT_UI_URL;
let runtimeUiUrl = uiUrl;

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
    await window.loadURL(runtimeUiUrl);
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

function recoveryActionFromUrl(url: string): RecoveryAction | undefined {
  if (!url.startsWith("elfienest://")) return undefined;
  const action = url.slice("elfienest://".length);
  if (
    action === "recover-data-home"
    || action === "choose-data-home"
    || action === "open-data-home"
    || action === "continue-start"
    || action === "quit"
  ) {
    return action;
  }
  return undefined;
}

function bindManagementWindow(window: BrowserWindow): void {
  window.webContents.on("will-navigate", (event, url) => {
    const action = recoveryActionFromUrl(url);
    if (action === undefined) return;
    event.preventDefault();
    recoveryActionHandler?.(action);
  });
  window.webContents.setWindowOpenHandler(({ url }) => {
    const action = recoveryActionFromUrl(url);
    if (action === undefined) return { action: "allow" };
    recoveryActionHandler?.(action);
    return { action: "deny" };
  });
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
  if (maintenanceStarted) return;
  maintenanceStarted = true;
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

async function continueAfterDataHomeRecovery(): Promise<void> {
  recoveryActionHandler = undefined;
  const window = managementWindow.current();
  const state = roleController?.state;
  if (window === undefined || state === undefined) return;
  if (state.kind === "failed") {
    showStartupFailure(window, new Error(state.reason));
    return;
  }
  runtimeUiAvailable = true;
  if (state.kind === "attached" || state.kind === "owned") {
    runtimeUiUrl = state.httpUrl ?? uiUrl;
  }
  await loadManagementUi(window);
  startOwnedRuntimeMaintenance();
}

async function handleDataHomeRecoveryAction(action: RecoveryAction): Promise<void> {
  const window = managementWindow.current();
  if (window === undefined || roleController === undefined) return;
  if (action === "quit") {
    requestExplicitApplicationExit();
    return;
  }
  if (action === "open-data-home") {
    const inspection = roleController.state.kind === "failed"
      ? roleController.state.recovery
      : undefined;
    if (inspection !== undefined) {
      await shell.openPath(inspection.home);
    }
    return;
  }
  if (action === "choose-data-home") {
    if (recoveryActionRunning) return;
    const selection = await dialog.showOpenDialog(window, {
      properties: ["openDirectory", "createDirectory"],
      title: "选择 ElfieNest 数据目录",
    });
    const selectedHome = selection.filePaths[0];
    if (selection.canceled || selectedHome === undefined) return;
    recoveryActionRunning = true;
    showStartupProgress(window, "starting");
    try {
      const state = await roleController.activateDataHome(selectedHome);
      if (state.kind === "failed") {
        if (state.recovery !== undefined) {
          showDataHomeRecovery(window, state.recovery);
        } else {
          showStartupFailure(window, new Error(state.reason));
        }
        return;
      }
      await continueAfterDataHomeRecovery();
    } finally {
      recoveryActionRunning = false;
    }
    return;
  }
  if (action === "continue-start") {
    await continueAfterDataHomeRecovery();
    return;
  }
  if (recoveryActionRunning) return;
  recoveryActionRunning = true;
  showStartupProgress(window, "starting");
  try {
    const state = await roleController.recoverDataHome();
    if (state.kind === "failed") {
      if (state.recovery !== undefined) {
        showDataHomeRecovery(window, state.recovery);
      } else {
        showStartupFailure(window, new Error(state.reason));
      }
      return;
    }
    const backupHome = roleController.lastRecovery?.backupHome;
    if (backupHome === undefined) {
      await continueAfterDataHomeRecovery();
      return;
    }
    recoveryActionHandler = (nextAction) => {
      void handleDataHomeRecoveryAction(nextAction);
    };
    showDataHomeRecoverySuccess(window, backupHome);
  } finally {
    recoveryActionRunning = false;
  }
}

async function startDesktop(): Promise<void> {
  // Controller calls the installed CLI for lifecycle commands. Mark that
  // child path so the CLI delegates to Core instead of starting another
  // Controller recursively.
  process.env["ELFIENEST_CONTROLLER_CLIENT"] = "1";
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
  const startup = roleController.start((phase) => {
    const window = managementWindow.current();
    if (window === undefined) return;
    if (phase === "core_ready") {
      runtimeUiAvailable = true;
      return;
    }
    if (!runtimeUiAvailable) {
      showStartupProgress(window, phase);
    }
  });
  controllerStartPromise = startup;
  controllerIpcServer = await startControllerIpcServer(app.getPath("userData"), {
    ACTIVATE_VIEWER: async () => {
      showManagementWindow();
      return { accepted: true, ...controllerStatePayload() };
    },
    ENSURE_SERVER: async () => {
      await ensureControllerRuntime();
      return { accepted: true, ...controllerStatePayload() };
    },
    STATUS: async () => controllerStatePayload(),
    STOP_SERVER: async () => {
      setImmediate(() => requestExplicitApplicationExit());
      return { accepted: true, state: "stopping" };
    },
  });
  const state = await startup;
  controllerStartPromise = undefined;
  if (state.kind === "failed") {
    if (state.recovery !== undefined) {
      recoveryActionHandler = (action) => {
        void handleDataHomeRecoveryAction(action);
      };
      const window = managementWindow.current() ?? ensureManagementWindow().window;
      showDataHomeRecovery(window, state.recovery);
      return;
    }
    throw new Error(state.reason);
  }
  const window = managementWindow.current();
  if (window !== undefined) {
    runtimeUiAvailable = true;
    if (state.kind === "attached" || state.kind === "owned") {
      runtimeUiUrl = state.httpUrl ?? uiUrl;
    }
    await loadManagementUi(window);
  }
}

function startDesktopUiRole(): void {
  app.setPath("userData", controllerHomeForAppData(app.getPath("appData")));
  const hasSingleInstanceLock = app.requestSingleInstanceLock();
  if (!hasSingleInstanceLock) {
    app.quit();
    return;
  }
  app.on("second-instance", (_event, commandLine) => {
    if (commandLine.includes("--background")) {
      void ensureControllerRuntime();
      return;
    }
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
      if (!controllerOnly) {
        showManagementWindow();
      }
      return startDesktop().then(() => {
        if (roleController?.state.kind !== "failed") {
          startOwnedRuntimeMaintenance();
        }
        if (controllerEnsurePending) {
          controllerEnsurePending = false;
          void ensureControllerRuntime();
        }
      });
    })
    .catch((error: unknown) => {
      const message = error instanceof Error ? error.message : "未知错误";
      console.error("ElfieNest Desktop 启动失败", message);
      if (controllerOnly) {
        app.quit();
        return;
      }
      const { window } = ensureManagementWindow();
      showStartupFailure(window, error);
      showManagementWindow();
    });
}

function controllerStatePayload(): Readonly<{ state: string; reason?: string }> {
  const state = roleController?.state;
  if (state === undefined) return { state: "starting" };
  if (state.kind === "failed") {
    return { state: "failed", reason: state.reason };
  }
  return { state: state.kind };
}

async function ensureControllerRuntime(): Promise<void> {
  if (roleController === undefined) {
    if (controllerStartPromise !== undefined) {
      await controllerStartPromise;
      return;
    }
    controllerEnsurePending = true;
    return;
  }
  try {
    const state = await roleController.ensureRuntime();
    if (state.kind === "failed") {
      console.error("ElfieNest Controller could not restore the Server", state.reason);
    }
  } catch (error: unknown) {
    const detail = error instanceof Error ? error.message : String(error);
    console.error("ElfieNest Controller restore failed", detail);
  }
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
    .finally(async () => {
      await controllerIpcServer?.close();
      controllerIpcServer = undefined;
      app.exit(0);
    });
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
