import type { MenuItemConstructorOptions } from "electron";

function explicitQuitItem(onExplicitQuit: () => void): MenuItemConstructorOptions {
  return {
    label: "退出 ElfieNest",
    accelerator: "CommandOrControl+Q",
    click: onExplicitQuit,
  };
}

export function applicationMenuTemplate(
  platform: NodeJS.Platform,
  onExplicitQuit: () => void,
): MenuItemConstructorOptions[] {
  const applicationMenu: MenuItemConstructorOptions =
    platform === "darwin"
      ? {
          label: "ElfieNest",
          submenu: [
            { role: "about" },
            { type: "separator" },
            { role: "hide" },
            { role: "hideOthers" },
            { role: "unhide" },
            { type: "separator" },
            explicitQuitItem(onExplicitQuit),
          ],
        }
      : {
          label: "文件",
          submenu: [explicitQuitItem(onExplicitQuit)],
        };
  return [
    applicationMenu,
    {
      label: "编辑",
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
      label: "窗口",
      submenu: [{ role: "minimize" }, { role: "close" }],
    },
  ];
}
