import { app, BrowserWindow } from "electron";
import { join } from "node:path";

const authorityNamespace =
  process.env.ELFIENEST_AUTHORITY_NAMESPACE ?? "elfienest.godot-authority";
const authorityUrl = process.env.ELFIENEST_GODOT_URL;
const AUTHORITY_LOAD_RETRY_DELAY_MS = 100;
const AUTHORITY_LOAD_MAX_ATTEMPTS = 1200;
let authorityWindow = null;
let shuttingDown = false;

if (authorityUrl === undefined || authorityUrl === "") {
  throw new Error("ELFIENEST_GODOT_URL is required for the Godot authority role");
}

if (process.platform === "darwin") {
  app.dock.hide();
}

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function loadAuthorityWindow() {
  let lastError;
  for (let attempt = 0; attempt < AUTHORITY_LOAD_MAX_ATTEMPTS; attempt += 1) {
    if (shuttingDown || authorityWindow === null || authorityWindow.isDestroyed()) {
      return;
    }
    try {
      await authorityWindow.loadURL(authorityUrl);
      return;
    } catch (error) {
      lastError = error;
      await wait(AUTHORITY_LOAD_RETRY_DELAY_MS);
    }
  }
  throw lastError ?? new Error("Godot authority Web page did not load");
}

function requestShutdown() {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  if (authorityWindow !== null && !authorityWindow.isDestroyed()) {
    authorityWindow.close();
  }
  // This process is a hidden authority child with no user-facing work to save.
  // app.quit() waits for Electron's asynchronous lifecycle while the parent
  // Supervisor is already waiting on this exact process group. Exit directly
  // so an explicit Runtime stop does not inherit Electron's multi-second tail.
  app.exit(0);
  process.exit(0);
}

process.once("SIGTERM", requestShutdown);
process.once("SIGINT", requestShutdown);

app.setPath("userData", join(app.getPath("userData"), authorityNamespace));

if (!app.requestSingleInstanceLock()) {
  requestShutdown();
} else {
  void app.whenReady().then(async () => {
    authorityWindow = new BrowserWindow({
      show: false,
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        backgroundThrottling: false,
      },
    });
    await loadAuthorityWindow();
  }).catch((error) => {
    console.error("ElfieNest Godot authority failed to load", error);
    requestShutdown();
  });
}
