type DesktopWifiAccessStatus =
  | "available"
  | "permission_denied"
  | "location_services_disabled"
  | "ssid_unavailable"
  | "permission_unknown"
  | "helper_timeout"
  | "helper_unavailable"
  | "unsupported"

type DesktopWifiAccessResult = Readonly<{
  status: DesktopWifiAccessStatus
  network_name: string | null
}>

declare global {
  interface Window {
    elfienestDesktop?: Readonly<{
      readCurrentWifiName: () => Promise<DesktopWifiAccessResult>
      openLocationSettings: () => Promise<void>
    }>
  }
}

export {}
