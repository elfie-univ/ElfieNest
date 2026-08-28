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

type DesktopRendererDiagnostic = Readonly<{
  origin: "window_error" | "unhandled_rejection" | "react_uncaught" | "react_recoverable"
  error_type: string
  message: string
  stack: string
  occurrences: number
  suppressed_count: number
}>

declare global {
  interface Window {
    elfienestDesktop?: Readonly<{
      readCurrentWifiName: () => Promise<DesktopWifiAccessResult>
      openLocationSettings: () => Promise<void>
      reportRendererError: (payload: DesktopRendererDiagnostic) => void
    }>
  }
}

export {}
