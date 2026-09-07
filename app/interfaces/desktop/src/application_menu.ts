import type { MenuItemConstructorOptions } from "electron";

export type ApplicationMenuLocale = "zh-CN" | "en-US";

const MENU_LABELS = {
  "zh-CN": {
    edit: "编辑",
    open: "打开管理窗口",
    quit: "退出 ElfieNest",
  },
  "en-US": {
    edit: "Edit",
    open: "Open Management Window",
    quit: "Quit ElfieNest",
  },
} as const satisfies Record<
  ApplicationMenuLocale,
  Readonly<Record<"edit" | "open" | "quit", string>>
>;

export function normalizeApplicationMenuLocale(systemLocale: string): ApplicationMenuLocale {
  return systemLocale.trim().toLowerCase().startsWith("en") ? "en-US" : "zh-CN";
}

// macOS routes the standard editing key equivalents (Cmd+C/V/X/A/Z) through
// the application menu's Edit roles, so removing the native menu entirely
// breaks copy and paste inside every input. Keep a minimal darwin-only menu
// with the system app menu and those roles; product navigation still lives
// in the web UI and tray, and Windows/Linux install no menu because
// Chromium handles those shortcuts natively there.
export function applicationMenuTemplate(
  platform: NodeJS.Platform,
  locale: ApplicationMenuLocale,
): MenuItemConstructorOptions[] | null {
  if (platform !== "darwin") {
    return null;
  }
  return [
    { role: "appMenu" },
    {
      label: MENU_LABELS[locale].edit,
      submenu: [
        { role: "undo" },
        { role: "redo" },
        { type: "separator" },
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        { role: "selectAll" },
      ],
    },
  ];
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
