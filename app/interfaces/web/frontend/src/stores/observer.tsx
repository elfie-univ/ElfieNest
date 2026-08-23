import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react"

import {
  closeObserverSession,
  nextObserverFrame,
  openObserverSession,
  warmObserverAssets,
  type ObserverCursor,
  type ObserverEntity,
  type ObserverFrame,
  type ObserverSubscription,
} from "../api/observer"
import { ApiError } from "../api/http"
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

const RENDERER_WARM_MILLISECONDS = 60 * 1000
const READY_TIMEOUT_MILLISECONDS = 20 * 1000
const READY_PROBE_MILLISECONDS = 250
const POLL_MILLISECONDS = 1000
const RETRY_MILLISECONDS = [1000, 2000, 5000, 10000] as const
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
      mock_motion: patch.mock_motion === undefined
        ? entity.mock_motion
        : patch.mock_motion,
    },
  }
}

function deltaNeedsSnapshot(
  frame: ObserverFrame,
  cursor: ObserverCursor | null,
  current: Readonly<Record<string, ObserverEntity>>,
): boolean {
  if (frame.kind === "snapshot") return false
  return cursor === null
    || frame.generation !== cursor.generation
    || frame.sequence !== cursor.sequence + 1
    || current[frame.entity_id] === undefined
}

function isAbortError(reason: unknown): boolean {
  return reason instanceof DOMException && reason.name === "AbortError"
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
  const pollAbortRef = useRef<AbortController | null>(null)
  const capabilityRef = useRef<string | null>(null)
  const activeScopeRef = useRef<string | null>(null)
  const scopeRef = useRef<ObserverScope | null>(null)
  const detachedRef = useRef(false)
  const engineReadyRef = useRef(false)
  const cursorRef = useRef<ObserverCursor | null>(null)
  const entitiesRef = useRef<Readonly<Record<string, ObserverEntity>>>({})
  const entityRevisionsRef = useRef<Readonly<Record<string, number>>>({})
  const semanticSnapshotRef = useRef<ObserverSemanticSnapshot | null>(null)
  const worldConfigRef = useRef<ObserverWorldConfig | null>(null)
  const restartRequiredRef = useRef(false)
  const attemptRef = useRef(0)
  const retryRef = useRef(0)
  const userPausedRef = useRef(false)
  const csrfTokenRef = useRef(csrfToken)
  csrfTokenRef.current = csrfToken
  const {
    cameraCatalog,
    clearCameraCatalog,
    overview,
    publishSemanticSnapshot,
    publishWorldConfig,
    reset,
    select,
    setLocalPresentationPaused: setBridgePresentationPaused,
  } = useObserverCameraBridge(iframeRef)

  const clearTimer = (timerRef: MutableRefObject<number | null>): void => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current)
    timerRef.current = null
  }

  const stopPolling = useCallback((): void => {
    clearTimer(pollTimerRef)
    pollAbortRef.current?.abort()
    pollAbortRef.current = null
  }, [])

  const destroyRenderer = useCallback((): void => {
    clearTimer(readyTimerRef)
    clearTimer(readinessProbeTimerRef)
    attemptRef.current += 1
    iframeRef.current?.remove()
    iframeRef.current = null
    engineReadyRef.current = false
    clearCameraCatalog()
  }, [clearCameraCatalog])

  const resetEngine = useCallback((): void => {
    stopPolling()
    destroyRenderer()
    capabilityRef.current = null
    activeScopeRef.current = null
    scopeRef.current = null
    worldConfigRef.current = null
    cursorRef.current = null
    retryRef.current = 0
    setStatus("idle")
    setFallbackReason(null)
    setEntities({})
    entitiesRef.current = {}
    entityRevisionsRef.current = {}
    semanticSnapshotRef.current = null
  }, [destroyRenderer, stopPolling])

  const closeCurrentSession = useCallback((keepalive = false): void => {
    stopPolling()
    const capability = capabilityRef.current
    capabilityRef.current = null
    activeScopeRef.current = null
    cursorRef.current = null
    retryRef.current = 0
    if (capability !== null && csrfTokenRef.current) {
      void closeObserverSession(
        capability,
        csrfTokenRef.current,
        keepalive,
      ).catch(() => {})
    }
  }, [stopPolling])

  const markEngineReady = useCallback((): void => {
    clearTimer(readyTimerRef)
    clearTimer(readinessProbeTimerRef)
    restartRequiredRef.current = false
    engineReadyRef.current = true
    setFallbackReason(null)
    publishWorldConfig(worldConfigRef.current)
    if (semanticSnapshotRef.current !== null) {
      publishSemanticSnapshot(semanticSnapshotRef.current)
    }
    if (!detachedRef.current && document.visibilityState !== "hidden") {
      setBridgePresentationPaused(userPausedRef.current)
      setStatus("ready")
    }
  }, [publishSemanticSnapshot, publishWorldConfig, setBridgePresentationPaused])

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
    destroyRenderer()
    restartRequiredRef.current = false
    setStatus("idle")
  }, [destroyRenderer])

  const requireRestart = useCallback((): void => {
    destroyRenderer()
    restartRequiredRef.current = true
    setFallbackReason("runtime")
    setStatus("fallback")
  }, [destroyRenderer])

  const openRef = useRef<(scope: ObserverScope) => Promise<void>>(async () => {})
  const pollRef = useRef<() => void>(() => {})
  pollRef.current = (): void => {
    pollTimerRef.current = null
    const capability = capabilityRef.current
    if (
      capability === null
      || detachedRef.current
      || document.visibilityState === "hidden"
    ) return
    const cursor = cursorRef.current
    const controller = new AbortController()
    pollAbortRef.current = controller
    void nextObserverFrame(capability, cursor, controller.signal)
      .then((frame) => {
        if (controller.signal.aborted || capabilityRef.current !== capability) return
        pollAbortRef.current = null
        retryRef.current = 0
        setFallbackReason(null)
        if (engineReadyRef.current) setStatus("ready")
        if (frame !== null) {
          if (deltaNeedsSnapshot(frame, cursor, entitiesRef.current)) {
            cursorRef.current = null
            pollTimerRef.current = window.setTimeout(() => pollRef.current(), 0)
            return
          }
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
        if (!detachedRef.current && document.visibilityState !== "hidden") {
          pollTimerRef.current = window.setTimeout(() => pollRef.current(), POLL_MILLISECONDS)
        }
      })
      .catch((reason: unknown) => {
        if (capabilityRef.current !== capability) return
        pollAbortRef.current = null
        if (isAbortError(reason)) return
        if (
          reason instanceof ApiError
          && (
            reason.status === 410
            || reason.code === "observer_session_expired"
            || reason.code === "observer_forbidden"
          )
        ) {
          capabilityRef.current = null
          activeScopeRef.current = null
          cursorRef.current = null
          const scope = scopeRef.current
          if (
            scope !== null
            && !detachedRef.current
            && document.visibilityState !== "hidden"
          ) {
            void openRef.current(scope)
          }
          return
        }
        if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
          setFallbackReason("disabled")
          setStatus("fallback")
          return
        }
        retryRef.current += 1
        const retryIndex = Math.min(retryRef.current - 1, RETRY_MILLISECONDS.length - 1)
        if (retryRef.current >= RETRY_MILLISECONDS.length) {
          setFallbackReason("runtime")
          setStatus("fallback")
        }
        if (!detachedRef.current && document.visibilityState !== "hidden") {
          pollTimerRef.current = window.setTimeout(
            () => pollRef.current(),
            RETRY_MILLISECONDS[retryIndex] ?? 10000,
          )
        }
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

  const pauseObservation = useCallback((): void => {
    stopPolling()
    setBridgePresentationPaused(true)
    clearTimer(releaseTimerRef)
    releaseTimerRef.current = window.setTimeout(
      releaseEngine,
      RENDERER_WARM_MILLISECONDS,
    )
    setStatus("idle")
  }, [releaseEngine, setBridgePresentationPaused, stopPolling])

  const detach = useCallback((): void => {
    attach(null)
    pauseObservation()
  }, [attach, pauseObservation])

  const open = useCallback(async (scope: ObserverScope): Promise<void> => {
    scopeRef.current = scope
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
    if (document.visibilityState === "hidden") {
      pauseObservation()
      return
    }
    clearTimer(releaseTimerRef)
    if (restartRequiredRef.current) {
      restartRequiredRef.current = false
    }
    setFallbackReason(null)
    setStatus("loading")
    const nextKey = scopeKey(scope)
    const attempt = attemptRef.current
    try {
      if (activeScopeRef.current !== null && activeScopeRef.current !== nextKey) {
        const previousCapability = capabilityRef.current
        stopPolling()
        capabilityRef.current = null
        activeScopeRef.current = null
        cursorRef.current = null
        if (previousCapability !== null) {
          void closeObserverSession(previousCapability, csrfToken).catch(() => {})
        }
      }
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
        stopPolling()
        const session = await openObserverSession(subscriptionFor(scope), csrfToken)
        if (attemptRef.current !== attempt) return
        capabilityRef.current = session.capability
        activeScopeRef.current = nextKey
        cursorRef.current = null
      }
      setBridgePresentationPaused(userPausedRef.current)
      if (pollAbortRef.current === null && pollTimerRef.current === null) pollRef.current()
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
  }, [createEngine, csrfToken, enabled, pauseObservation, publishWorldConfig, requireRestart, setBridgePresentationPaused, stopPolling])
  openRef.current = open

  useEffect(() => {
    if (!enabled) return undefined
    const timer = window.setTimeout(() => { void warmObserverAssets() }, 1)
    return (): void => window.clearTimeout(timer)
  }, [enabled])

  useEffect(() => {
    if (!enabled) resetEngine()
  }, [enabled, resetEngine])

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

  useEffect(() => {
    const resume = (): void => {
      const scope = scopeRef.current
      if (scope !== null && !detachedRef.current) void openRef.current(scope)
    }
    const onVisibilityChange = (): void => {
      if (document.visibilityState === "hidden") {
        pauseObservation()
        return
      }
      resume()
    }
    const onPageHide = (event: PageTransitionEvent): void => {
      if (event.persisted) {
        pauseObservation()
        return
      }
      closeCurrentSession(true)
      destroyRenderer()
    }
    const onFreeze = (): void => {
      pauseObservation()
      releaseEngine()
    }
    const onOffline = (): void => stopPolling()
    document.addEventListener("visibilitychange", onVisibilityChange)
    window.addEventListener("pagehide", onPageHide)
    document.addEventListener("freeze", onFreeze)
    window.addEventListener("offline", onOffline)
    window.addEventListener("online", resume)
    return (): void => {
      document.removeEventListener("visibilitychange", onVisibilityChange)
      window.removeEventListener("pagehide", onPageHide)
      document.removeEventListener("freeze", onFreeze)
      window.removeEventListener("offline", onOffline)
      window.removeEventListener("online", resume)
    }
  }, [closeCurrentSession, destroyRenderer, pauseObservation, releaseEngine, stopPolling])

  useEffect(() => () => {
    closeCurrentSession(true)
    destroyRenderer()
  }, [closeCurrentSession, destroyRenderer])

  const setLocalPresentationPaused = useCallback((paused: boolean): void => {
    userPausedRef.current = paused
    if (!detachedRef.current && document.visibilityState !== "hidden") {
      setBridgePresentationPaused(paused)
    }
  }, [setBridgePresentationPaused])

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
