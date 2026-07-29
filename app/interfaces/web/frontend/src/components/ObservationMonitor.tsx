import { useState } from "react"

import { Button } from "@/components/ui/button"
import { useOptionalObserver } from "../stores/observer"
import { Icon } from "./Icon"
import { ObserverSurface } from "./ObserverSurface"

type ObservationMonitorProps = {
  readonly roomId: string
}

export function ObservationMonitor({ roomId }: ObservationMonitorProps) {
  const observer = useOptionalObserver()
  const [toolbarVisible, setToolbarVisible] = useState(true)
  const cameraCatalog = observer?.cameraCatalog ?? null
  const cameraViews = cameraCatalog?.views.filter((view) => view.id !== "overview") ?? []
  const presentationPaused = cameraCatalog?.presentationPaused ?? false
  const pauseIcon = presentationPaused ? "play" : "pause"
  const pauseLabel = presentationPaused ? "继续观察" : "暂停观察"
  const cameraCommandDisabled = observer === null || presentationPaused

  return <section className="observation-monitor" data-slot="observation-monitor">
    <ObserverSurface autoStart kind="room" roomId={roomId} showHeader={false} title="房间 3D 观察" />
    {toolbarVisible ? <div aria-label="监控工具栏" className="observation-monitor__toolbar" role="toolbar">
      <Button aria-label="复位视角" className="observation-monitor__command" disabled={cameraCommandDisabled} onClick={() => observer?.reset()} size="sm" type="button" variant="outline">
        <Icon name="rotate-ccw" size={16} /><span>复位</span>
      </Button>
      <Button aria-label="总览" aria-pressed={cameraCatalog?.activeId === "overview"} className="observation-monitor__command" disabled={cameraCommandDisabled} onClick={() => observer?.overview()} size="sm" type="button" variant="outline">
        <Icon name="cctv" size={16} /><span>总览</span>
      </Button>
      {cameraViews.map((view) => <Button aria-label={view.label} aria-pressed={cameraCatalog?.activeId === view.id} className="observation-monitor__camera" disabled={cameraCommandDisabled} key={view.id} onClick={() => observer?.select(view.id)} size="sm" type="button" variant="outline">{view.label}</Button>)}
      <Button aria-label={pauseLabel} className="observation-monitor__command observation-monitor__pause" disabled={observer === null} onClick={() => observer?.setLocalPresentationPaused(!presentationPaused)} size="sm" type="button" variant="outline">
        <Icon name={pauseIcon} size={16} /><span>{pauseLabel}</span>
      </Button>
      <Button aria-label="隐藏工具栏" className="observation-monitor__hide" data-tooltip="隐藏工具栏" onClick={() => setToolbarVisible(false)} size="icon-sm" title="隐藏工具栏" type="button" variant="outline">
        <Icon name="eye-off" size={16} />
      </Button>
    </div> : <Button aria-label="显示工具栏" className="observation-monitor__restore" data-tooltip="显示工具栏" onClick={() => setToolbarVisible(true)} size="icon-sm" title="显示工具栏" type="button" variant="outline">
      <Icon name="eye" size={16} />
    </Button>}
  </section>
}
