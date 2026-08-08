import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react"

import {
  OBSERVER_CAMERA_COMMAND_KIND,
  OBSERVER_CHANNEL,
  OBSERVER_PROTOCOL_VERSION,
  parseObserverCameraCatalog,
  parseObserverCameraCommand,
  parseObserverSemanticSnapshot,
  parseObserverWorldConfig,
  type ObserverCameraCatalog,
  type ObserverCameraCommand,
  type ObserverSemanticSnapshot,
} from "./observer-protocol"

export const PRODUCT_OBSERVER_URL = "/runtime/godot/elfienest.html?observer=product" as const

export type ObserverCameraBridge = {
  readonly cameraCatalog: ObserverCameraCatalog | null
  readonly clearCameraCatalog: () => void
  readonly overview: () => void
  readonly publishSemanticSnapshot: (candidate: unknown) => void
  readonly publishWorldConfig: (candidate: unknown) => void
  readonly reset: () => void
  readonly select: (viewId: string) => void
  readonly setLocalPresentationPaused: (paused: boolean) => void
}

function currentSameOriginEngine(
  iframeRef: RefObject<HTMLIFrameElement | null>,
): HTMLIFrameElement | null {
  const engine = iframeRef.current
  if (engine === null || engine.contentWindow === null) return null
  const expectedUrl = new URL(PRODUCT_OBSERVER_URL, window.location.origin)
  const currentUrl = new URL(engine.src, window.location.origin)
  if (currentUrl.origin !== window.location.origin || currentUrl.href !== expectedUrl.href) return null
  return engine
}

export function useObserverCameraBridge(
  iframeRef: RefObject<HTMLIFrameElement | null>,
): ObserverCameraBridge {
  const [cameraCatalog, setCameraCatalog] = useState<ObserverCameraCatalog | null>(null)
  const cameraCatalogRef = useRef<ObserverCameraCatalog | null>(null)

  const clearCameraCatalog = useCallback((): void => {
    cameraCatalogRef.current = null
    setCameraCatalog(null)
  }, [])

  const postCameraCommand = useCallback((candidate: unknown): void => {
    const command = parseObserverCameraCommand(candidate)
    const engine = currentSameOriginEngine(iframeRef)
    if (command === null || engine === null || engine.contentWindow === null) return
    const catalog = cameraCatalogRef.current
    if (
      catalog?.presentationPaused === true
      && (command.action !== "set_local_presentation_paused" || command.paused !== false)
    ) return
    engine.contentWindow.postMessage(command, window.location.origin)
  }, [iframeRef])

  const overview = useCallback((): void => {
    const command = {
      channel: OBSERVER_CHANNEL,
      version: OBSERVER_PROTOCOL_VERSION,
      kind: OBSERVER_CAMERA_COMMAND_KIND,
      action: "overview",
    } satisfies ObserverCameraCommand
    postCameraCommand(command)
  }, [postCameraCommand])

  const select = useCallback((viewId: string): void => {
    const catalog = cameraCatalogRef.current
    if (catalog === null || !catalog.views.some((view) => view.id === viewId)) return
    const command = {
      channel: OBSERVER_CHANNEL,
      version: OBSERVER_PROTOCOL_VERSION,
      kind: OBSERVER_CAMERA_COMMAND_KIND,
      action: "select",
      view_id: viewId,
    } satisfies ObserverCameraCommand
    postCameraCommand(command)
  }, [postCameraCommand])

  const reset = useCallback((): void => {
    const command = {
      channel: OBSERVER_CHANNEL,
      version: OBSERVER_PROTOCOL_VERSION,
      kind: OBSERVER_CAMERA_COMMAND_KIND,
      action: "reset",
    } satisfies ObserverCameraCommand
    postCameraCommand(command)
  }, [postCameraCommand])

  const setLocalPresentationPaused = useCallback((paused: boolean): void => {
    const command = {
      channel: OBSERVER_CHANNEL,
      version: OBSERVER_PROTOCOL_VERSION,
      kind: OBSERVER_CAMERA_COMMAND_KIND,
      action: "set_local_presentation_paused",
      paused,
    } satisfies ObserverCameraCommand
    postCameraCommand(command)
  }, [postCameraCommand])

  const publishSemanticSnapshot = useCallback((candidate: unknown): void => {
    const snapshot = parseObserverSemanticSnapshot(candidate)
    if (snapshot === null) return
    const engine = currentSameOriginEngine(iframeRef)
    if (engine === null || engine.contentWindow === null) return
    engine.contentWindow.postMessage(snapshot, window.location.origin)
  }, [iframeRef])

  const publishWorldConfig = useCallback((candidate: unknown): void => {
    const config = parseObserverWorldConfig(candidate)
    if (config === null) return
    const engine = currentSameOriginEngine(iframeRef)
    if (engine === null || engine.contentWindow === null) return
    engine.contentWindow.postMessage(config, window.location.origin)
  }, [iframeRef])

  useEffect(() => {
    const onMessage = (event: MessageEvent<unknown>): void => {
      const engine = currentSameOriginEngine(iframeRef)
      if (event.origin !== window.location.origin || event.source !== engine?.contentWindow) return
      const nextCatalog = parseObserverCameraCatalog(event.data)
      const currentCatalog = cameraCatalogRef.current
      if (nextCatalog === null || (currentCatalog !== null && nextCatalog.revision < currentCatalog.revision)) return
      cameraCatalogRef.current = nextCatalog
      setCameraCatalog(nextCatalog)
    }
    window.addEventListener("message", onMessage)
    return (): void => window.removeEventListener("message", onMessage)
  }, [iframeRef])

  return useMemo<ObserverCameraBridge>(() => ({
    cameraCatalog,
    clearCameraCatalog,
    overview,
    publishSemanticSnapshot,
    publishWorldConfig,
    reset,
    select,
    setLocalPresentationPaused,
  }), [cameraCatalog, clearCameraCatalog, overview, publishSemanticSnapshot, publishWorldConfig, reset, select, setLocalPresentationPaused])
}
