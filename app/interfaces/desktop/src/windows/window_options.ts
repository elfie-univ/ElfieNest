import type { BrowserWindowConstructorOptions } from "electron";

const DEFAULT_BACKGROUND_COLOR = "#fffaf1";
export const DEFAULT_MANAGEMENT_UI_URL = "http://127.0.0.1:8000/";
export const MACOS_CONTENT_INSET_CSS = `
@media (min-width: 641px) {
  .manage-sidebar,
  .setup-rail,
  .app-rail {
    padding-top: 50px !important;
  }
  .observation-monitor--standalone .observation-monitor__back {
    top: 50px !important;
  }
}`;

export function mainWindowOptions(
  platform: NodeJS.Platform,
): BrowserWindowConstructorOptions {
  const common: BrowserWindowConstructorOptions = {
    title: "ElfieNest",
    width: 1440,
    height: 960,
    minWidth: 1024,
    minHeight: 720,
    backgroundColor: DEFAULT_BACKGROUND_COLOR,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  };
  if (platform !== "darwin") {
    return common;
  }
  return {
    ...common,
    titleBarStyle: "hiddenInset",
    trafficLightPosition: { x: 16, y: 16 },
  };
}

export function closeKeepsBackgroundServiceRunning(
  explicitExitRequested: boolean,
): boolean {
  return !explicitExitRequested;
}
