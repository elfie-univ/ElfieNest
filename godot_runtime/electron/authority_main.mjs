import { app, BrowserWindow } from "electron";
import { join } from "node:path";

const authorityNamespace =
  process.env.ELFIENEST_AUTHORITY_NAMESPACE ?? "elfienest.godot-authority";
const authorityUrl = process.env.ELFIENEST_GODOT_URL;
let authorityWindow = null;

if (authorityUrl === undefined || authorityUrl === "") {
  throw new Error("ELFIENEST_GODOT_URL is required for the Godot authority role");
}

app.setPath("userData", join(app.getPath("userData"), authorityNamespace));

if (!app.requestSingleInstanceLock()) {
  app.quit();
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
    await authorityWindow.loadURL(authorityUrl);
  });
}
