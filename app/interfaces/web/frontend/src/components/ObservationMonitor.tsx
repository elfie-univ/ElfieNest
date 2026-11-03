import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { elfies, type ElfieProfile } from "../api/elfies/profiles"
import { adminElfies } from "../api/admin/elfies"

import { Button } from "@/components/ui/button"
import { ButtonGroup } from "@/components/ui/button-group"
import { useOptionalObserver } from "../stores/observer"
import { createObserverWorldConfig } from "../stores/observer-protocol"
import { Icon } from "./Icon"
import { ObserverSurface } from "./ObserverSurface"
import { SelectField } from "./SelectField"

// Identification markers match the current estate model's EXTERIOR M01–M08 materials.
const BEDROOM_MARKER_COLORS: Readonly<Record<string, string>> = {
  "01": "#95b58c", "02": "#d39bae", "03": "#91bbd7", "04": "#d5a078",
  "05": "#83bbb5", "06": "#b8a2ce", "07": "#d8cc92", "08": "#8791bc",
}

type ObservationMonitorProps = {
  readonly elfieScope?: "owned" | "all"
  readonly immersive?: boolean
  readonly mode?: "embedded" | "standalone"
  readonly onExitImmersive?: () => void
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

export function ObservationMonitor({ elfieScope = "owned", immersive = false, mode = "embedded", onExitImmersive, roomId }: ObservationMonitorProps) {
  const { t } = useTranslation("monitor")
  const observer = useOptionalObserver()
  const cameraCatalog = observer?.cameraCatalog ?? null
  const cameraViews = cameraCatalog?.views.filter((view) => view.id === "overview" || view.id === "estate-ring" || /^(central-[1-4]|dorm-0[1-8]|terrace-0[1-8])$/.test(view.id)) ?? []
  const groupedCameraOptions = [
    { label: t("controls.outdoorViews"), options: cameraViews.filter((view) => view.id === "overview" || view.id === "estate-ring") },
    { label: t("controls.centralViews"), options: cameraViews.filter((view) => view.id.startsWith("central-")) },
    { label: t("controls.bedroomViews"), options: cameraViews.filter((view) => /^(dorm|terrace)-/.test(view.id)).sort((a, b) => Number(a.id.slice(-2)) - Number(b.id.slice(-2)) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)) },
  ].map((group) => ({ label: group.label, options: group.options.map((view) => {
    const markerColor = /^(dorm|terrace)-/.test(view.id) ? BEDROOM_MARKER_COLORS[view.id.slice(-2)] : undefined
    return { value: view.id, label: view.label, ...(markerColor === undefined ? {} : { markerColor }) }
  }) }))
    .filter((group) => group.options.length > 0)
  const [viewMode, setViewMode] = useState<"fixed" | "elfie">("fixed")
  const [availableElfies, setAvailableElfies] = useState<readonly ElfieProfile[]>([])
  const [elfieLoad, setElfieLoad] = useState<"loading" | "ready" | "error">("loading")
  const [selectedElfie, setSelectedElfie] = useState("")
  const [elfieView, setElfieView] = useState<"follow" | "first_person">("follow")
  useEffect(() => {
    let current = true
    setAvailableElfies([])
    setElfieLoad("loading")
    if (observer?.status !== "ready") return () => { current = false }
    const request = elfieScope === "all"
      ? adminElfies().then((items) => items.map((item) => item.profile))
      : elfies("owned").then((items) => items.filter((item) => item.relationship === "owned"))
    void request.then((items) => {
      if (!current) return
      setAvailableElfies(items)
      setElfieLoad("ready")
    }, () => { if (current) setElfieLoad("error") })
    return () => { current = false }
  }, [roomId, observer?.status, elfieScope])
  const actorViewId = (id: string, perspective: "follow" | "first_person") => `${perspective === "follow" ? "elfie-" : "elfie-pov-"}${id}`
  const canObserve = (id: string, perspective: "follow" | "first_person") => cameraCatalog?.views.some((view) => view.id === actorViewId(id, perspective)) ?? false
  const chooseElfie = (id: string, perspective: "follow" | "first_person") => {
    if (!availableElfies.some((elfie) => elfie.elfie_id === id) || !canObserve(id, perspective)) return
    setSelectedElfie(id)
    setElfieView(perspective)
    observer?.select(actorViewId(id, perspective))
  }
  const chooseViewMode = (value: string) => {
    if ((value !== "fixed" && value !== "elfie") || value === viewMode) return
    setViewMode(value)
    if (value === "fixed") {
      observer?.select("overview")
    } else {
      const candidate = availableElfies.find((elfie) => elfie.elfie_id === selectedElfie && canObserve(elfie.elfie_id, elfieView))
        ?? availableElfies.find((elfie) => canObserve(elfie.elfie_id, elfieView))
      if (candidate) chooseElfie(candidate.elfie_id, elfieView)
    }
  }
  const elfieOptions = availableElfies.map((elfie) => ({
    value: elfie.elfie_id,
    label: `${elfie.name || elfie.elfie_id}${canObserve(elfie.elfie_id, elfieView) ? "" : ` · ${t("controls.notInScene")}`}`,
    disabled: !canObserve(elfie.elfie_id, elfieView),
  }))
  const presentationPaused = cameraCatalog?.presentationPaused ?? false
  const pauseIcon = presentationPaused ? "play" : "pause"
  const pauseLabel = presentationPaused ? t("controls.resume") : t("controls.pause")
  const cameraCommandDisabled = observer === null || observer.status !== "ready" || presentationPaused
  const pauseCommandDisabled = observer === null || observer.status !== "ready"
  const observedElfieCount = Object.keys(observer?.entities ?? {}).length
  const statusKey = monitorStatusKey(observer?.status ?? null)
  const statusCopy = statusKey === "connection.connectedTo" || statusKey === "status.loading"
    ? t(statusKey, { endpoint: roomId })
    : t(statusKey)
  const showStatusOverlay = statusKey !== "connection.connectedTo"
  const retryAvailable = statusKey === "status.fallback"
    && observer !== null
    && observer.fallbackReason !== "insecure-context"

  const showToolbar = mode === "embedded" || !immersive
  const monitorClassName = [
    "observation-monitor",
    mode === "standalone" ? "observation-monitor--standalone" : "",
    immersive ? "observation-monitor--immersive" : "",
  ].filter(Boolean).join(" ")
  return <section className={monitorClassName} data-slot="observation-monitor">
    <div className="observation-monitor__stage">
      <ObserverSurface autoStart kind="room" roomId={roomId} showHeader={false} title={t("surface.title")} />
      {showStatusOverlay ? <div aria-live="polite" className="observer-surface__fallback absolute inset-0 z-[2]" role="status">
        <p>{statusCopy}</p>
        <p>{t(monitorHelpKey(statusKey, observer?.fallbackReason))}</p>
        {retryAvailable ? <Button aria-label={t("controls.retry")} onClick={() => { void observer.openRoom(roomId, createObserverWorldConfig(roomId)) }} type="button">{t("controls.retry")}</Button> : null}
      </div> : <p aria-live="polite" className="sr-only" role="status">{statusCopy}</p>}
      {statusKey === "connection.connectedTo" ? <p aria-live="polite" className="observation-monitor__entity-count">{t("surface.entityCount", { count: observedElfieCount })}</p> : null}
      <p className="sr-only">{t("help.controls")}</p>
      {cameraViews.length === 0 ? <p className="sr-only">{t("empty.cameras")}</p> : null}
      {showToolbar ? <div aria-label={t("toolbar.label")} className="observation-monitor__toolbar" role="toolbar">
        <div className="observation-monitor__views" role="group" aria-label={t("controls.viewGroup")}>
          <ButtonGroup aria-label={t("controls.viewMode")} className="observation-monitor__mode">
            <Button aria-pressed={viewMode === "fixed"} disabled={cameraCommandDisabled} onClick={() => chooseViewMode("fixed")} type="button" variant="outline">{t("controls.fixedViews")}</Button>
            <Button aria-pressed={viewMode === "elfie"} disabled={cameraCommandDisabled} onClick={() => chooseViewMode("elfie")} type="button" variant="outline">{t("controls.elfieViews")}</Button>
          </ButtonGroup>
          {viewMode === "fixed" ? <>
            <div className="observation-monitor__selector"><SelectField disabled={cameraCommandDisabled || cameraCatalog === null} label={t("controls.view")} onValueChange={(value) => observer?.select(value)} options={groupedCameraOptions} value={cameraCatalog?.activeId ?? "overview"} /></div>
            <Button aria-label={t("controls.resetAria")} className="observation-monitor__command" disabled={cameraCommandDisabled || cameraCatalog === null} onClick={() => observer?.reset()} type="button" variant="outline">
              <Icon name="rotate-ccw" size={16} /><span>{t("controls.reset")}</span>
            </Button>
          </> : <>
            <div className="observation-monitor__selector"><SelectField disabled={cameraCommandDisabled || elfieOptions.length === 0} label={t("controls.elfie")} value={selectedElfie} onValueChange={(value) => chooseElfie(value, elfieView)} options={elfieOptions} placeholder={t(elfieLoad === "loading" ? "controls.loadingElfies" : elfieLoad === "error" ? "controls.elfiesError" : "controls.noElfies")} /></div>
            <div className="observation-monitor__selector"><SelectField disabled={cameraCommandDisabled || !selectedElfie || !canObserve(selectedElfie, elfieView)} label={t("controls.elfiePerspective")} value={elfieView} onValueChange={(value) => { if (value === "follow" || value === "first_person") chooseElfie(selectedElfie, value) }} options={[
              { value: "follow", label: t("controls.follow") }, { value: "first_person", label: t("controls.firstPerson") },
            ]} /></div>
          </>}
        </div>
        <div className="observation-monitor__playback" role="group" aria-label={t("controls.playbackGroup")}>
        <Button aria-label={pauseLabel} className="observation-monitor__command observation-monitor__pause" disabled={pauseCommandDisabled} onClick={() => observer?.setLocalPresentationPaused(!presentationPaused)} type="button" variant="outline">
          <Icon name={pauseIcon} size={16} /><span>{pauseLabel}</span>
        </Button>
        </div>
      </div> : null}
    </div>
    {immersive && onExitImmersive ? <Button aria-label={t("navigation.exitImmersive")} className="observation-monitor__exit-immersive" data-tooltip={t("navigation.exitImmersive")} onClick={onExitImmersive} size="icon" title={t("navigation.exitImmersive")} type="button" variant="outline">
      <Icon name="panel-left-open" size={18} />
    </Button> : null}
  </section>
}
