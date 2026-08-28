import type { MenuItemConstructorOptions } from "electron";

export type ApplicationMenuLocale = "zh-CN" | "en-US";

// Product navigation lives in the web UI and tray, so no native application
// menu is installed on Windows, Linux, or macOS.
export const APPLICATION_MENU: null = null;

const MENU_LABELS = {
  "zh-CN": {
    open: "打开管理窗口",
    quit: "退出 ElfieNest",
  },
  "en-US": {
    open: "Open Management Window",
    quit: "Quit ElfieNest",
  },
} as const satisfies Record<
  ApplicationMenuLocale,
  Readonly<Record<"open" | "quit", string>>
>;

export function normalizeApplicationMenuLocale(systemLocale: string): ApplicationMenuLocale {
  return systemLocale.trim().toLowerCase().startsWith("en") ? "en-US" : "zh-CN";
}

function explicitQuitItem(
  onExplicitQuit: () => void,
  label: string,
): MenuItemConstructorOptions {
  return {
    label,
    accelerator: "CommandOrControl+Q",
    click: onExplicitQuit,
  };
}

export function backgroundMenuTemplate(
  onOpenWindow: () => void,
  onExplicitQuit: () => void,
  locale: ApplicationMenuLocale,
): MenuItemConstructorOptions[] {
  const labels = MENU_LABELS[locale];
  return [
    { label: labels.open, click: onOpenWindow },
    { type: "separator" },
    explicitQuitItem(onExplicitQuit, labels.quit),
  ];
}
