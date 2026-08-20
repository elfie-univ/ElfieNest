const { contextBridge, ipcRenderer } = require("electron") as Pick<
  typeof import("electron"),
  "contextBridge" | "ipcRenderer"
>;

contextBridge.exposeInMainWorld("elfienestDesktop", {
  readCurrentWifiName: () => ipcRenderer.invoke("mobile-network:read-current-wifi"),
  openLocationSettings: () => ipcRenderer.invoke("mobile-network:open-location-settings"),
});
