import { useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { useOptionalObserver } from "../stores/observer"
import { createObserverWorldConfig } from "../stores/observer-protocol"
import { Icon } from "./Icon"
import { ObserverSurface } from "./ObserverSurface"

type ObservationMonitorProps = {
  readonly bedCount: number
  readonly roomId: string
}

type MonitorStatusKey =
  | "connection.connectedTo"
  | "status.fallback"
  | "status.idle"
  | "status.loading"
  | "status.offline"
  | "status.unknown"

type MonitorHelpKey =
  | "help.disabled"
  | "help.idle"
  | "help.insecureContext"
  | "help.loading"
  | "help.offline"
  | "help.runtime"
  | "help.unknown"
  | "help.unsupportedDevice"

export function monitorStatusKey(status: unknown): MonitorStatusKey {
  switch (status) {
    case null: return "status.offline"
    case "idle": return "status.idle"
    case "loading": return "status.loading"
    case "ready": return "connection.connectedTo"
    case "fallback": return "status.fallback"
    default: return "status.unknown"
  }
}

function monitorHelpKey(
  statusKey: MonitorStatusKey,
  fallbackReason: unknown,
): MonitorHelpKey {
  if (statusKey === "status.idle") return "help.idle"
  if (statusKey === "status.loading") return "help.loading"
  if (statusKey === "status.offline") return "help.offline"
  if (statusKey === "status.unknown") return "help.unknown"
  switch (fallbackReason) {
    case "disabled": return "help.disabled"
    case "insecure-context": return "help.insecureContext"
    case "unsupported-device": return "help.unsupportedDevice"
    case "runtime": return "help.runtime"
    default: return "help.unknown"
  }
}

export function ObservationMonitor({ bedCount, roomId }: ObservationMonitorProps) {
  const { t } = useTranslation("monitor")
  const observer = useOptionalObserver()
  const [toolbarVisible, setToolbarVisible] = useState(true)
  const cameraCatalog = observer?.cameraCatalog ?? null
  const cameraViews = cameraCatalog?.views.filter((view) => view.id !== "overview") ?? []
  const presentationPaused = cameraCatalog?.presentationPaused ?? false
  const pauseIcon = presentationPaused ? "play" : "pause"
  const pauseLabel = presentationPaused ? t("controls.resume") : t("controls.pause")
  const cameraCommandDisabled = observer === null || presentationPaused
  const statusKey = monitorStatusKey(observer?.status ?? null)
  const statusCopy = statusKey === "connection.connectedTo" || statusKey === "status.loading"
    ? t(statusKey, { endpoint: roomId })
    : t(statusKey)
  const showStatusOverlay = statusKey !== "connection.connectedTo"
  const retryAvailable = statusKey === "status.fallback"
    && observer !== null
    && observer.fallbackReason !== "insecure-context"

  return <section className="observation-monitor" data-slot="observation-monitor">
    <ObserverSurface autoStart bedCount={bedCount} kind="room" roomId={roomId} showHeader={false} title={t("surface.title")} />
    {showStatusOverlay ? <div aria-live="polite" className="observer-surface__fallback absolute inset-0 z-[2]" role="status">
      <p>{statusCopy}</p>
      <p>{t(monitorHelpKey(statusKey, observer?.fallbackReason))}</p>
      {retryAvailable ? <Button aria-label={t("controls.retry")} onClick={() => { void observer.openRoom(roomId, createObserverWorldConfig(roomId, bedCount)) }} type="button">{t("controls.retry")}</Button> : null}
    </div> : <p aria-live="polite" className="sr-only" role="status">{statusCopy}</p>}
    <p className="sr-only">{t("help.controls")}</p>
    {cameraViews.length === 0 ? <p className="sr-only">{t("empty.cameras")}</p> : null}
    {toolbarVisible ? <div aria-label={t("toolbar.label")} className="observation-monitor__toolbar" role="toolbar">
      <Button aria-label={t("controls.resetAria")} className="observation-monitor__command" disabled={cameraCommandDisabled} onClick={() => observer?.reset()} size="sm" type="button" variant="outline">
        <Icon name="rotate-ccw" size={16} /><span>{t("controls.reset")}</span>
      </Button>
      <Button aria-label={t("controls.overview")} aria-pressed={cameraCatalog?.activeId === "overview"} className="observation-monitor__command" disabled={cameraCommandDisabled} onClick={() => observer?.overview()} size="sm" type="button" variant="outline">
        <Icon name="cctv" size={16} /><span>{t("controls.overview")}</span>
      </Button>
      {cameraViews.map((view) => <Button aria-label={view.label} aria-pressed={cameraCatalog?.activeId === view.id} className="observation-monitor__camera" disabled={cameraCommandDisabled} key={view.id} onClick={() => observer?.select(view.id)} size="sm" type="button" variant="outline">{view.label}</Button>)}
      <Button aria-label={pauseLabel} className="observation-monitor__command observation-monitor__pause" disabled={observer === null} onClick={() => observer?.setLocalPresentationPaused(!presentationPaused)} size="sm" type="button" variant="outline">
        <Icon name={pauseIcon} size={16} /><span>{pauseLabel}</span>
      </Button>
      <Button aria-label={t("controls.hide")} className="observation-monitor__hide" data-tooltip={t("controls.hide")} onClick={() => setToolbarVisible(false)} size="icon-sm" title={t("controls.hide")} type="button" variant="outline">
        <Icon name="eye-off" size={16} />
      </Button>
    </div> : <Button aria-label={t("controls.show")} className="observation-monitor__restore" data-tooltip={t("controls.show")} onClick={() => setToolbarVisible(true)} size="icon-sm" title={t("controls.show")} type="button" variant="outline">
      <Icon name="eye" size={16} />
    </Button>}
  </section>
}
