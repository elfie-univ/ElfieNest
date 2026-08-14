import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react"

import {
  nextObserverFrame,
  openObserverSession,
  warmObserverAssets,
  type ObserverCursor,
  type ObserverEntity,
  type ObserverFrame,
  type ObserverSubscription,
} from "../api/observer"
import { PRODUCT_OBSERVER_URL, useObserverCameraBridge } from "./observer-camera-bridge"
import {
  OBSERVER_CHANNEL,
  OBSERVER_PROTOCOL_VERSION,
  OBSERVER_SEMANTIC_SNAPSHOT_KIND,
  type ObserverCameraCatalog,
  type ObserverSemanticSnapshot,
  type ObserverWorldConfig,
} from "./observer-protocol"

declare global {
  interface Window {
    __elfieNestObserverReady?: boolean
  }
}

export type ObserverStatus = "idle" | "loading" | "ready" | "fallback"
export type ObserverFallbackReason = "disabled" | "insecure-context" | "unsupported-device" | "runtime"
type ObserverScope =
  | { readonly kind: "room"; readonly roomId: string; readonly worldConfig: ObserverWorldConfig }
  | { readonly kind: "elfie"; readonly elfieId: string }
type ObserverState = {
  readonly attach: (target: HTMLElement | null) => void
  readonly cameraCatalog: ObserverCameraCatalog | null
  readonly configureRoom: (worldConfig: ObserverWorldConfig) => void
  readonly detach: () => void
  readonly entities: Readonly<Record<string, ObserverEntity>>
  readonly openElfie: (elfieId: string) => Promise<void>
  readonly openRoom: (roomId: string, worldConfig: ObserverWorldConfig) => Promise<void>
  readonly fallbackReason: ObserverFallbackReason | null
  readonly overview: () => void
  readonly reset: () => void
  readonly select: (viewId: string) => void
  readonly setLocalPresentationPaused: (paused: boolean) => void
  readonly status: ObserverStatus
}

const IDLE_RELEASE_MILLISECONDS = 5 * 60 * 1000
const READY_TIMEOUT_MILLISECONDS = 20 * 1000
const READY_PROBE_MILLISECONDS = 250
const POLL_MILLISECONDS = 1000
const ObserverContext = createContext<ObserverState | null>(null)

function subscriptionFor(scope: ObserverScope): ObserverSubscription {
  return scope.kind === "room"
    ? { kind: "room", room_id: scope.roomId }
    : { kind: "elfie", elfie_id: scope.elfieId }
}

function scopeKey(scope: ObserverScope): string {
  return scope.kind === "room" ? `room:${scope.roomId}` : `elfie:${scope.elfieId}`
}

function supportsWebGl2(): boolean {
  const canvas = document.createElement("canvas")
  return canvas.getContext("webgl2") !== null
}

function isLowMemoryDevice(): boolean {
  const value = Reflect.get(navigator, "deviceMemory")
  return typeof value === "number" && value > 0 && value < 2
}

function isPrivateLanIpv4(hostname: string): boolean {
  const octets = hostname.split(".")
  if (octets.length !== 4 || octets.some((octet) => !/^\d+$/.test(octet))) return false
  const values = octets.map(Number)
  if (values.some((octet) => !Number.isInteger(octet) || octet < 0 || octet > 255)) return false
  const [first = -1, second = -1] = values
  return first === 127
    || first === 10
    || (first === 172 && second >= 16 && second <= 31)
    || (first === 192 && second === 168)
}

export function isObserverContextAllowed(
  location: Pick<Location, "hostname" | "protocol"> = window.location,
  secureContext: boolean = window.isSecureContext,
): boolean {
  if (secureContext === true) return true
  return location.protocol === "http:" && isPrivateLanIpv4(location.hostname)
}

function mergeFrame(
  frame: ObserverFrame,
  current: Readonly<Record<string, ObserverEntity>>,
): Readonly<Record<string, ObserverEntity>> {
  if (frame.kind === "snapshot") return frame.entities
  const entity = current[frame.entity_id]
  if (entity === undefined) return current
  const patch = frame.patch
  return {
    ...current,
    [frame.entity_id]: {
      room_id: patch.room_id ?? entity.room_id,
      zone_id: patch.zone_id === undefined ? entity.zone_id : patch.zone_id,
      posture: patch.posture ?? entity.posture,
      active: patch.active ?? entity.active,
      active_command_id: patch.active_command_id === undefined
        ? entity.active_command_id
        : patch.active_command_id,
      species_id: patch.species_id === undefined ? entity.species_id : patch.species_id,
      appearance: patch.appearance === undefined ? entity.appearance : patch.appearance,
      home_anchor_id: patch.home_anchor_id === undefined
        ? entity.home_anchor_id
        : patch.home_anchor_id,
    },
  }
}

function semanticScope(scope: ObserverSubscription): ObserverSemanticSnapshot["scope"] {
  return scope.kind === "room"
    ? { kind: "room", room_id: scope.room_id }
    : { kind: "elfie", elfie_id: scope.elfie_id }
}

export function ObserverProvider({
  children,
  csrfToken,
  enabled,
}: {
  readonly children: ReactNode
  readonly csrfToken: string
  readonly enabled: boolean
}) {
  const [status, setStatus] = useState<ObserverStatus>("idle")
  const [fallbackReason, setFallbackReason] = useState<ObserverFallbackReason | null>(null)
  const [entities, setEntities] = useState<Readonly<Record<string, ObserverEntity>>>({})
  const parkingRef = useRef<HTMLDivElement | null>(null)
  const targetRef = useRef<HTMLElement | null>(null)
  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  const releaseTimerRef = useRef<number | null>(null)
  const readyTimerRef = useRef<number | null>(null)
  const readinessProbeTimerRef = useRef<number | null>(null)
  const pollTimerRef = useRef<number | null>(null)
  const capabilityRef = useRef<string | null>(null)
  const activeScopeRef = useRef<string | null>(null)
  const detachedRef = useRef(false)
  const engineReadyRef = useRef(false)
  const cursorRef = useRef<ObserverCursor | null>(null)
  const entitiesRef = useRef<Readonly<Record<string, ObserverEntity>>>({})
  const entityRevisionsRef = useRef<Readonly<Record<string, number>>>({})
  const semanticSnapshotRef = useRef<ObserverSemanticSnapshot | null>(null)
  const worldConfigRef = useRef<ObserverWorldConfig | null>(null)
  const restartRequiredRef = useRef(false)
  const attemptRef = useRef(0)
  const {
    cameraCatalog,
    clearCameraCatalog,
    overview,
    publishSemanticSnapshot,
    publishWorldConfig,
    reset,
    select,
    setLocalPresentationPaused,
  } = useObserverCameraBridge(iframeRef)

  const clearTimer = (timerRef: MutableRefObject<number | null>): void => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current)
    timerRef.current = null
  }

  const resetEngine = useCallback((): void => {
    clearTimer(readyTimerRef)
    clearTimer(readinessProbeTimerRef)
    clearTimer(pollTimerRef)
    attemptRef.current += 1
    iframeRef.current?.remove()
    iframeRef.current = null
    engineReadyRef.current = false
    capabilityRef.current = null
    activeScopeRef.current = null
    worldConfigRef.current = null
    cursorRef.current = null
    setStatus("idle")
    setFallbackReason(null)
    setEntities({})
    entitiesRef.current = {}
    entityRevisionsRef.current = {}
    semanticSnapshotRef.current = null
    clearCameraCatalog()
  }, [clearCameraCatalog])

  const markEngineReady = useCallback((): void => {
    clearTimer(readyTimerRef)
    clearTimer(readinessProbeTimerRef)
    restartRequiredRef.current = false
    engineReadyRef.current = true
    setFallbackReason(null)
    publishWorldConfig(worldConfigRef.current)
    if (!detachedRef.current) setStatus("ready")
  }, [publishWorldConfig])

  const configureRoom = useCallback((worldConfig: ObserverWorldConfig): void => {
    worldConfigRef.current = worldConfig
    if (engineReadyRef.current) publishWorldConfig(worldConfig)
  }, [publishWorldConfig])

  const exportLooksReady = (engine: HTMLIFrameElement): boolean => {
    try {
      if (engine.contentWindow?.__elfieNestObserverReady === true) return true
      const document = engine.contentDocument
      if (document === null) return false
      const canvas = document.querySelector("#canvas")
      const statusElement = document.querySelector<HTMLElement>("#status")
      if (canvas === null) return false
      if (statusElement === null) return true
      const style = window.getComputedStyle(statusElement)
      return statusElement.hidden || style.display === "none" || style.visibility === "hidden"
    } catch (reason: unknown) {
      if (reason instanceof DOMException) return false
      throw reason
    }
  }

  const probeExportReadiness = useCallback((engine: HTMLIFrameElement): void => {
    clearTimer(readinessProbeTimerRef)
    const probe = (): void => {
      if (iframeRef.current !== engine || engineReadyRef.current) return
      if (exportLooksReady(engine)) {
        markEngineReady()
        return
      }
      readinessProbeTimerRef.current = window.setTimeout(probe, READY_PROBE_MILLISECONDS)
    }
    readinessProbeTimerRef.current = window.setTimeout(probe, READY_PROBE_MILLISECONDS)
  }, [markEngineReady])

  const releaseEngine = useCallback((): void => {
    clearTimer(releaseTimerRef)
    resetEngine()
    restartRequiredRef.current = false
    setStatus("idle")
  }, [resetEngine])

  const requireRestart = useCallback((): void => {
    resetEngine()
    restartRequiredRef.current = true
    setFallbackReason("runtime")
    setStatus("fallback")
  }, [resetEngine])

  const pollRef = useRef<() => void>(() => {})
  pollRef.current = (): void => {
    const capability = capabilityRef.current
    if (capability === null) return
    void nextObserverFrame(capability, cursorRef.current)
      .then((frame) => {
        if (capabilityRef.current !== capability) return
        if (frame !== null) {
          cursorRef.current = { generation: frame.generation, sequence: frame.sequence }
          const nextEntities = mergeFrame(frame, entitiesRef.current)
          entitiesRef.current = nextEntities
          setEntities(nextEntities)
          entityRevisionsRef.current = frame.kind === "snapshot"
            ? frame.entity_revisions
            : { ...entityRevisionsRef.current, [frame.entity_id]: frame.entity_revision }
          semanticSnapshotRef.current = {
            channel: OBSERVER_CHANNEL,
            version: OBSERVER_PROTOCOL_VERSION,
            kind: OBSERVER_SEMANTIC_SNAPSHOT_KIND,
            protocol: 3,
            generation: frame.generation,
            sequence: frame.sequence,
            scope: semanticScope(frame.scope),
            entities: { ...nextEntities },
            entity_revisions: { ...entityRevisionsRef.current },
          }
        }
        if (semanticSnapshotRef.current !== null) {
          publishSemanticSnapshot(semanticSnapshotRef.current)
        }
        pollTimerRef.current = window.setTimeout(() => pollRef.current(), POLL_MILLISECONDS)
      })
      .catch((reason: unknown) => {
        if (capabilityRef.current !== capability) return
        if (reason instanceof Error) {
          requireRestart()
          return
        }
        throw reason
      })
  }

  const createEngine = useCallback((): HTMLIFrameElement => {
    const engine = document.createElement("iframe")
    engine.className = "observer-engine"
    engine.src = PRODUCT_OBSERVER_URL
    engine.title = "ElfieNest 3D Observer"
    engine.addEventListener("error", requireRestart)
    return engine
  }, [requireRestart])

  const attach = useCallback((target: HTMLElement | null): void => {
    targetRef.current = target
    detachedRef.current = target === null
    const engine = iframeRef.current
    const parent = target ?? parkingRef.current
    if (engine !== null && parent !== null && engine.parentElement !== parent) parent.appendChild(engine)
  }, [])

  const detach = useCallback((): void => {
    attach(null)
    setStatus("idle")
    clearTimer(releaseTimerRef)
    releaseTimerRef.current = window.setTimeout(releaseEngine, IDLE_RELEASE_MILLISECONDS)
  }, [attach, releaseEngine])

  const open = useCallback(async (scope: ObserverScope): Promise<void> => {
    worldConfigRef.current = scope.kind === "room" ? scope.worldConfig : null
    if (!enabled || !csrfToken) {
      setFallbackReason("disabled")
      setStatus("fallback")
      return
    }
    if (!isObserverContextAllowed()) {
      setFallbackReason("insecure-context")
      setStatus("fallback")
      return
    }
    if (!supportsWebGl2() || isLowMemoryDevice()) {
      setFallbackReason("unsupported-device")
      setStatus("fallback")
      return
    }
    clearTimer(releaseTimerRef)
    if (restartRequiredRef.current) {
      resetEngine()
      restartRequiredRef.current = false
    }
    setFallbackReason(null)
    setStatus("loading")
    const nextKey = scopeKey(scope)
    const attempt = attemptRef.current
    try {
      if (iframeRef.current === null) {
        const engine = createEngine()
        iframeRef.current = engine
        const parent = targetRef.current ?? parkingRef.current
        parent?.appendChild(engine)
        probeExportReadiness(engine)
        clearTimer(readyTimerRef)
        readyTimerRef.current = window.setTimeout(requireRestart, READY_TIMEOUT_MILLISECONDS)
      }
      if (activeScopeRef.current !== nextKey || capabilityRef.current === null) {
        clearTimer(pollTimerRef)
        const capability = await openObserverSession(subscriptionFor(scope), csrfToken)
        if (attemptRef.current !== attempt) return
        capabilityRef.current = capability
        activeScopeRef.current = nextKey
        cursorRef.current = null
        pollRef.current()
      }
      if (engineReadyRef.current) {
        publishWorldConfig(worldConfigRef.current)
        setStatus("ready")
      }
    } catch (reason: unknown) {
      if (attemptRef.current !== attempt) return
      if (reason instanceof Error) {
        requireRestart()
        return
      }
      throw reason
    }
  }, [createEngine, csrfToken, enabled, publishWorldConfig, requireRestart, resetEngine])

  useEffect(() => {
    if (!enabled) return undefined
    const timer = window.setTimeout(() => { void warmObserverAssets() }, 1)
    return (): void => window.clearTimeout(timer)
  }, [enabled])

  useEffect(() => {
    if (!enabled) releaseEngine()
  }, [enabled, releaseEngine])

  useEffect(() => {
    const onMessage = (event: MessageEvent<unknown>): void => {
      const engine = iframeRef.current
      if (event.origin !== window.location.origin || event.source !== engine?.contentWindow) return
      if (event.data !== "elfienest:godot-web-ready") return
      markEngineReady()
    }
    window.addEventListener("message", onMessage)
    return (): void => window.removeEventListener("message", onMessage)
  }, [markEngineReady])

  useEffect(() => releaseEngine, [releaseEngine])

  const value = useMemo<ObserverState>(() => ({
    attach,
    cameraCatalog,
    configureRoom,
    detach,
    entities,
    openElfie: async (elfieId: string): Promise<void> => open({ kind: "elfie", elfieId }),
    openRoom: async (roomId: string, worldConfig: ObserverWorldConfig): Promise<void> => open({ kind: "room", roomId, worldConfig }),
    fallbackReason,
    overview,
    reset,
    select,
    setLocalPresentationPaused,
    status,
  }), [attach, cameraCatalog, configureRoom, detach, entities, fallbackReason, open, overview, reset, select, setLocalPresentationPaused, status])

  return <ObserverContext.Provider value={value}>{children}<div aria-hidden className="observer-engine-parking" ref={parkingRef} /></ObserverContext.Provider>
}

export function useOptionalObserver(): ObserverState | null {
  return useContext(ObserverContext)
}
