import type { MenuItemConstructorOptions } from "electron";

export type ApplicationMenuLocale = "zh-CN" | "en-US";

const MENU_LABELS = {
  "zh-CN": {
    file: "文件",
    edit: "编辑",
    window: "窗口",
    open: "打开管理窗口",
    hideWindow: "隐藏管理窗口",
    quit: "退出 ElfieNest",
  },
  "en-US": {
    file: "File",
    edit: "Edit",
    window: "Window",
    open: "Open Management Window",
    hideWindow: "Hide Management Window",
    quit: "Quit ElfieNest",
  },
} as const satisfies Record<
  ApplicationMenuLocale,
  Readonly<Record<"file" | "edit" | "window" | "open" | "hideWindow" | "quit", string>>
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

export function applicationMenuTemplate(
  platform: NodeJS.Platform,
  onOpenWindow: () => void,
  onHideWindow: () => void,
  onExplicitQuit: () => void,
  locale: ApplicationMenuLocale,
): MenuItemConstructorOptions[] {
  const labels = MENU_LABELS[locale];
  const applicationMenu: MenuItemConstructorOptions =
    platform === "darwin"
      ? {
          label: "ElfieNest",
          submenu: [
            { role: "about" },
            { type: "separator" },
            { label: labels.open, click: onOpenWindow },
            { label: labels.hideWindow, accelerator: "CommandOrControl+W", click: onHideWindow },
            { type: "separator" },
            { role: "hide" },
            { role: "hideOthers" },
            { role: "unhide" },
            { type: "separator" },
            explicitQuitItem(onExplicitQuit, labels.quit),
          ],
        }
      : {
          label: labels.file,
          submenu: [
            { label: labels.open, click: onOpenWindow },
            { label: labels.hideWindow, accelerator: "CommandOrControl+W", click: onHideWindow },
            { type: "separator" },
            explicitQuitItem(onExplicitQuit, labels.quit),
          ],
        };
  return [
    applicationMenu,
    {
      label: labels.edit,
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
    {
      label: labels.window,
      submenu: [
        { role: "minimize" },
        { label: labels.hideWindow, accelerator: "CommandOrControl+W", click: onHideWindow },
      ],
    },
  ];
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
