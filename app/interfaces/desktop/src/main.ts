import {
  app,
  BrowserWindow,
  crashReporter,
  ipcMain,
  Menu,
  nativeImage,
  shell,
  Tray,
} from "electron";
import { randomUUID } from "node:crypto";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";

import {
  APPLICATION_MENU,
  backgroundMenuTemplate,
  normalizeApplicationMenuLocale,
} from "./application_menu.js";
import {
  DesktopRoleController,
  type DesktopRoleState,
} from "./desktop_role_lifecycle.js";
import {
  DesktopDiagnostics,
  installDesktopProcessExceptionHandlers,
  normalizeRendererDiagnosticPayload,
  pruneCrashDumps,
} from "./diagnostics.js";
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
import {
  LOCATION_SERVICES_SETTINGS_URL,
  readCurrentWifiName,
} from "./mobile_network_access.js";
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
} from "./windows/window_options.js";
import { SingleWindowRegistry } from "./windows/window_registry.js";

let roleController: DesktopRoleController | undefined;
let explicitExitRequested = false;
let exitInProgress = false;
let requestedExitReason = "not-requested";
const managementWindow = new SingleWindowRegistry<BrowserWindow>();
let backgroundTray: Tray | undefined;
let maintenanceTimer: NodeJS.Timeout | undefined;
let maintenanceRunning = false;
let maintenanceStarted = false;
let lastMaintenanceFailure: string | undefined;
let runtimeUiAvailable = false;
let managementUiLoaded = false;
let recoveryActionHandler: ((action: RecoveryAction) => void) | undefined;
let recoveryActionRunning = false;
let controllerIpcServer: ControllerIpcServer | undefined;
const controllerOnly = process.argv.includes("--background");
let controllerEnsurePending = false;
let controllerStartPromise: Promise<DesktopRoleState> | undefined;
let desktopDiagnostics: DesktopDiagnostics | undefined;
let removeProcessExceptionHandlers: (() => void) | undefined;
let diagnosticsTimer: NodeJS.Timeout | undefined;

type RecoveryAction =
  | "recover-data-home"
  | "open-data-home"
  | "continue-start"
  | "quit";

const configuredUiUrl = process.env["ELFIENEST_UI_URL"];
let runtimeUiUrl = configuredUiUrl;

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
  if (
    managementUiLoaded
    || !runtimeUiAvailable
    || runtimeUiUrl === undefined
    || window.isDestroyed()
  ) return;
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
    || action === "open-data-home"
    || action === "continue-start"
    || action === "quit"
  ) {
    return action;
  }
  return undefined;
}

function bindManagementWindow(window: BrowserWindow): void {
  window.webContents.on("did-finish-load", () => {
    desktopDiagnostics?.event("management_page_ready");
  });
  window.on("unresponsive", () => {
    desktopDiagnostics?.event("management_window_unresponsive", {}, "error");
  });
  window.on("responsive", () => {
    desktopDiagnostics?.event("management_window_responsive");
  });
  window.webContents.on(
    "did-fail-load",
    (_event, errorCode, errorDescription, _validatedUrl, isMainFrame) => {
      desktopDiagnostics?.event(
        "management_page_load_failed",
        {
          exit_code: errorCode,
          message: errorDescription,
          is_main_frame: isMainFrame,
        },
        "error",
      );
    },
  );
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
          if (lastMaintenanceFailure !== state.reason) {
            lastMaintenanceFailure = state.reason;
            console.error("ElfieNest background Runtime recovery failed", state.reason);
            desktopDiagnostics?.event(
              "runtime_maintenance_failed",
              { message: state.reason },
              "error",
            );
          }
        } else {
          lastMaintenanceFailure = undefined;
        }
      })
      .catch((error: unknown) => {
        desktopDiagnostics?.error("runtime_maintenance_rejected", error);
        const message = error instanceof Error ? error.message : String(error);
        console.error("ElfieNest background Runtime maintenance rejected", message);
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
    runtimeUiUrl = state.httpUrl ?? configuredUiUrl;
  }
  if (runtimeUiUrl === undefined) {
    showStartupFailure(window, new Error("Runtime did not publish an HTTP endpoint"));
    return;
  }
  await loadManagementUi(window);
  startOwnedRuntimeMaintenance();
}

async function handleDataHomeRecoveryAction(action: RecoveryAction): Promise<void> {
  const window = managementWindow.current();
  if (window === undefined || roleController === undefined) return;
  if (action === "quit") {
    requestExplicitApplicationExit("data-home-recovery-quit");
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
    const manifest = loadAndValidateResourceManifest(
      process.resourcesPath,
      app.getVersion(),
    );
    process.env["ELFIENEST_SOURCE_REVISION"] = manifest.source_revision;
    desktopDiagnostics?.setSourceRevision(manifest.source_revision);
    desktopDiagnostics?.event("desktop_build_attribution", {
      application_version: manifest.application_version,
      target: manifest.target,
    });
    console.info(
      "ElfieNest Desktop build",
      manifest.application_version,
      manifest.source_revision,
      manifest.target,
    );
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
    ACTIVATE_VIEWER: async (payload) => {
      await assertControllerTarget(payload);
      showManagementWindow();
      return { accepted: true, ...controllerStatePayload() };
    },
    ENSURE_SERVER: async (payload) => {
      assertConfiguredControllerTarget(payload);
      await ensureControllerRuntime();
      await assertControllerTarget(payload);
      return { accepted: true, ...controllerStatePayload() };
    },
    STATUS: async (payload) => {
      await assertControllerTarget(payload);
      return controllerStatePayload();
    },
    STOP_SERVER: async (payload) => {
      await assertControllerTarget(payload);
      setImmediate(() => requestExplicitApplicationExit("controller-stop-server"));
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
  if (state.kind === "attached" || state.kind === "owned") {
    // A background Controller has no window during initial startup. Keep the
    // ready Runtime URL available so a later single-instance activation can
    // create the Viewer and load the real management page.
    runtimeUiAvailable = true;
    runtimeUiUrl = state.httpUrl ?? configuredUiUrl;
    if (runtimeUiUrl === undefined) {
      throw new Error("Runtime did not publish an HTTP endpoint");
    }
  }
  const window = managementWindow.current();
  if (window !== undefined) {
    if (runtimeUiUrl === undefined) {
      throw new Error("Runtime did not publish an HTTP endpoint");
    }
    await loadManagementUi(window);
  }
}

function startDesktopUiRole(): void {
  Menu.setApplicationMenu(APPLICATION_MENU);
  const configuredAppData = process.env["ELFIENEST_DESKTOP_APP_DATA"]?.trim();
  const controllerHome = controllerHomeForAppData(
    configuredAppData === undefined || configuredAppData === ""
      ? app.getPath("appData")
      : configuredAppData,
  );
  app.setPath("userData", controllerHome);
  const hasSingleInstanceLock = app.requestSingleInstanceLock();
  if (!hasSingleInstanceLock) {
    requestedExitReason = "secondary-instance";
    console.info("ElfieNest Desktop exit requested", requestedExitReason);
    app.quit();
    return;
  }
  try {
    desktopDiagnostics = new DesktopDiagnostics(
      join(controllerHome, "logs", "desktop-events.jsonl"),
      {
        role: "desktop",
        sourceRevision: process.env["ELFIENEST_SOURCE_REVISION"],
      },
    );
    removeProcessExceptionHandlers = installDesktopProcessExceptionHandlers(
      desktopDiagnostics,
    );
  } catch (error: unknown) {
    console.error("ElfieNest Desktop diagnostics unavailable", error);
  }
  try {
    crashReporter.start({
      companyName: "ElfieNest",
      productName: "ElfieNest",
      uploadToServer: false,
      compress: true,
    });
  } catch (error: unknown) {
    desktopDiagnostics?.error("crash_reporter_start_failed", error);
  }
  try {
    pruneCrashDumps(app.getPath("crashDumps"));
  } catch (error: unknown) {
    desktopDiagnostics?.error("crash_dump_prune_failed", error);
  }
  if (desktopDiagnostics !== undefined) {
    desktopDiagnostics.event("desktop_process_started", {
      controller_only: controllerOnly,
    });
    startDesktopResourceMonitor();
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
      desktopDiagnostics?.error("desktop_start_failed", error);
      const message = error instanceof Error ? error.message : "未知错误";
      console.error("ElfieNest Desktop 启动失败", message);
      if (controllerOnly) {
        requestedExitReason = "controller-start-failure";
        console.info("ElfieNest Desktop exit requested", requestedExitReason);
        app.quit();
        return;
      }
      const { window } = ensureManagementWindow();
      showStartupFailure(window, error);
      showManagementWindow();
    });
}

function startDesktopResourceMonitor(): void {
  if (diagnosticsTimer !== undefined) return;
  const sample = (): void => {
    const memory = process.memoryUsage();
    const cpu = process.cpuUsage();
    desktopDiagnostics?.event("process_resource_sample", {
      rss_bytes: memory.rss,
      heap_used_bytes: memory.heapUsed,
      heap_total_bytes: memory.heapTotal,
      external_bytes: memory.external,
      cpu_user_microseconds: cpu.user,
      cpu_system_microseconds: cpu.system,
      active_resource_count: process.getActiveResourcesInfo().length,
    });
  };
  sample();
  diagnosticsTimer = setInterval(sample, 300_000);
  diagnosticsTimer.unref?.();
}

function controllerStatePayload(): Readonly<{
  state: string;
  reason?: string;
  data_home?: string;
  controller_protocol: number;
}> {
  const state = roleController?.state;
  if (state === undefined) return { state: "starting", controller_protocol: 2 };
  if (state.kind === "failed") {
    return {
      state: "failed",
      reason: state.reason,
      ...(state.recovery === undefined ? {} : { data_home: state.recovery.home }),
      controller_protocol: 2,
    };
  }
  if (state.kind === "stopped") return { state: "stopped", controller_protocol: 2 };
  return {
    state: state.kind,
    data_home: state.dataHome,
    controller_protocol: 2,
  };
}

async function assertControllerTarget(
  payload: Readonly<Record<string, unknown>>,
): Promise<void> {
  assertConfiguredControllerTarget(payload);
  if (controllerStartPromise !== undefined) {
    await controllerStartPromise;
  }
  const expected = payload.expected_data_home;
  if (typeof expected !== "string" || expected.trim() === "") {
    throw new Error("Controller request is missing expected_data_home");
  }
  const expectedPath = resolveControllerDataHome(expected);
  const actual = controllerStatePayload().data_home;
  if (actual === undefined || resolveControllerDataHome(actual) !== expectedPath) {
    throw new Error(
      `Controller data root mismatch: expected=${expectedPath} actual=${actual ?? "unknown"}`,
    );
  }
}

function assertConfiguredControllerTarget(
  payload: Readonly<Record<string, unknown>>,
): void {
  const expected = payload.expected_data_home;
  if (typeof expected !== "string" || expected.trim() === "") {
    throw new Error("Controller request is missing expected_data_home");
  }
  const configured = configuredControllerDataHome();
  const expectedPath = resolveControllerDataHome(expected);
  if (expectedPath !== configured) {
    throw new Error(
      `Controller configured data root mismatch: expected=${expectedPath} configured=${configured}`,
    );
  }
}

function configuredControllerDataHome(): string {
  const configured = process.env["ELFIE_HOME"]?.trim();
  const raw = configured === undefined || configured === ""
    ? join(homedir(), ".elfienest")
    : configured;
  return resolveControllerDataHome(raw);
}

function resolveControllerDataHome(value: string): string {
  const trimmed = value.trim();
  if (trimmed === "~") return homedir();
  if (trimmed.startsWith("~/")) {
    return resolve(homedir(), trimmed.slice(2));
  }
  return resolve(homedir(), trimmed);
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
      desktopDiagnostics?.event(
        "controller_runtime_restore_failed",
        { message: state.reason },
        "error",
      );
      console.error("ElfieNest Controller could not restore the Server", state.reason);
    }
  } catch (error: unknown) {
    desktopDiagnostics?.error("controller_runtime_restore_rejected", error);
    const detail = error instanceof Error ? error.message : String(error);
    console.error("ElfieNest Controller restore failed", detail);
  }
}

ipcMain.handle("mobile-network:read-current-wifi", async () => {
  return readCurrentWifiName({
    platform: process.platform,
    resourcesPath: process.resourcesPath,
  });
});

ipcMain.handle("mobile-network:open-location-settings", async () => {
  if (process.platform === "darwin") {
    await shell.openExternal(LOCATION_SERVICES_SETTINGS_URL);
  }
});

ipcMain.on("diagnostics:renderer-error", (event, payload: unknown) => {
  const window = managementWindow.current();
  if (window === undefined || event.sender.id !== window.webContents.id) return;
  const fields = normalizeRendererDiagnosticPayload(payload);
  if (fields === undefined) return;
  desktopDiagnostics?.event(
    "renderer_error",
    fields,
    fields["origin"] === "react_recoverable" ? "warning" : "error",
  );
});

app.on("before-quit", (event) => {
  console.info("ElfieNest Desktop before-quit", requestedExitReason);
  desktopDiagnostics?.event("desktop_before_quit", {
    reason: requestedExitReason,
  });
  if (!explicitExitRequested || exitInProgress) {
    return;
  }
  event.preventDefault();
  explicitExitRequested = false;
  exitInProgress = true;
  const cleanup = roleController?.exitApplication() ?? Promise.resolve();
  void cleanup
    .catch((error: unknown) => {
      desktopDiagnostics?.error("runtime_cleanup_failed", error);
      const message = error instanceof Error ? error.message : String(error);
      console.error("ElfieNest Runtime cleanup during quit failed", message);
    })
    .finally(async () => {
      await controllerIpcServer?.close();
      controllerIpcServer = undefined;
      console.info("ElfieNest Desktop cleanup complete", requestedExitReason);
      app.exit(0);
    });
});

app.on("activate", () => {
  showManagementWindow();
});

app.on("window-all-closed", () => {
  if (backgroundTray === undefined && process.platform !== "darwin") {
    requestedExitReason = "window-all-closed";
    console.info("ElfieNest Desktop exit requested", requestedExitReason);
    app.quit();
  }
});

app.on("quit", (_event, exitCode) => {
  console.info("ElfieNest Desktop exited", requestedExitReason, exitCode);
  desktopDiagnostics?.event("desktop_process_exited", {
    reason: requestedExitReason,
    exit_code: exitCode,
  });
  if (diagnosticsTimer !== undefined) {
    clearInterval(diagnosticsTimer);
    diagnosticsTimer = undefined;
  }
  removeProcessExceptionHandlers?.();
  removeProcessExceptionHandlers = undefined;
  desktopDiagnostics?.close();
});

app.on("render-process-gone", (_event, webContents, details) => {
  desktopDiagnostics?.event(
    "render_process_gone",
    {
      web_contents_id: webContents.id,
      reason: details.reason,
      exit_code: details.exitCode,
    },
    "critical",
  );
});

app.on("child-process-gone", (_event, details) => {
  desktopDiagnostics?.event(
    "child_process_gone",
    {
      component: details.type,
      reason: details.reason,
      exit_code: details.exitCode,
      name: details.name,
      service_name: details.serviceName,
    },
    "error",
  );
});

export function requestExplicitApplicationExit(
  reason = "user-request",
): void {
  if (exitInProgress) {
    return;
  }
  requestedExitReason = reason;
  console.info("ElfieNest Desktop exit requested", requestedExitReason);
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

startDesktopUiRole();
