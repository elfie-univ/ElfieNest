import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import type { PublicProfile } from "./model"
import {
  createProfileGodotPreview,
  measureVisibleFrame,
  ProfileGodotPreviewError,
  toGodotVisibleFrameMetrics,
  type ProfileGodotPreview,
} from "./profile-godot-preview"

const PROFILE_GODOT_PREVIEW_URL = "/runtime/godot/elfienest.html?mode=elfie_lab"

export type PreviewStatus = "idle" | "loading" | "ready" | "unavailable" | "error"

type ProfileGodotViewportProps = {
  readonly onPreviewChange: (preview: ProfileGodotPreview | null) => void
  readonly onStageChange: (stage: HTMLDivElement | null) => void
  readonly onStatusChange: (status: PreviewStatus) => void
  readonly profile: PublicProfile
}

type PointerPosition = { readonly id: number; readonly x: number; readonly y: number }

export function ProfileGodotViewport({
  onPreviewChange,
  onStageChange,
  onStatusChange,
  profile,
}: ProfileGodotViewportProps) {
  const { t } = useTranslation("chat")
  const frameRef = useRef<HTMLIFrameElement>(null)
  const previewRef = useRef<ProfileGodotPreview | null>(null)
  const pointerRef = useRef<PointerPosition | null>(null)
  const [status, setStatusState] = useState<PreviewStatus>("loading")
  const [error, setError] = useState("")
  const appearanceRevision = previewRevision(profile)

  function setStatus(nextStatus: PreviewStatus): void {
    setStatusState(nextStatus)
    onStatusChange(nextStatus)
  }

  useEffect(() => {
    setStatus("loading")
    setError("")
    const frame = frameRef.current
    if (frame === null) return undefined
    let active = true
    let calibrationStarted = false
    let bridge: ProfileGodotPreview | null = null
    const pendingActions = new Map<string, { readonly resolve: () => void; readonly reject: (reason: unknown) => void }>()
    const waitForAction = (action: string): Promise<void> => new Promise<void>((resolve, reject) => {
      pendingActions.set(action, { resolve, reject })
    })
    const calibrateVisibleFrame = async (): Promise<void> => {
      const currentBridge = bridge
      if (currentBridge === null) throw new ProfileGodotPreviewError("preview_not_ready")
      const provisional = await currentBridge.capture()
      try {
        const metrics = await measureVisibleFrame(provisional.blob)
        if (metrics === null) return
        const completion = waitForAction("frame")
        currentBridge.send("frame", toGodotVisibleFrameMetrics(metrics))
        await completion
      } finally {
        if (typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(provisional.previewUrl)
      }
    }
    bridge = createProfileGodotPreview({
      frame,
      onEvent: (event) => {
        if (event.kind === "ready") {
          if (profile.runtimeAppearance === null) {
            setStatus("unavailable")
            return
          }
          try {
            bridge?.send("configure", {
              appearance: profile.runtimeAppearance,
              elfie_id: profile.elfieId,
              spec_revision: previewRevision(profile),
              species_id: profile.speciesId,
            })
          } catch (reason) {
            reportPreviewError(reason, setStatus, setError, t("profile.appearance.error"))
          }
          return
        }
        if (event.kind === "completed") {
          const pending = pendingActions.get(event.action)
          if (pending !== undefined) {
            pendingActions.delete(event.action)
            pending.resolve()
            return
          }
          if (event.action === "configure" && !calibrationStarted) {
            calibrationStarted = true
            void calibrateVisibleFrame()
              .then(() => {
                if (!active) return
                setStatus("ready")
                setError("")
              })
              .catch((reason: unknown) => {
                if (active) reportPreviewError(reason, setStatus, setError, t("profile.appearance.error"))
              })
          }
          return
        }
        if (event.kind === "unsupported") {
          const pending = pendingActions.get(event.action)
          if (pending !== undefined) {
            pendingActions.delete(event.action)
            pending.reject(new ProfileGodotPreviewError(event.reason))
          }
          reportPreviewError(
            new ProfileGodotPreviewError(event.reason),
            setStatus,
            setError,
            t("profile.appearance.error"),
          )
        }
      },
    })
    previewRef.current = bridge
    onPreviewChange(bridge)
    return () => {
      active = false
      for (const pending of pendingActions.values()) pending.reject(new ProfileGodotPreviewError("preview_closed"))
      pendingActions.clear()
      bridge?.dispose()
      if (previewRef.current === bridge) previewRef.current = null
      onPreviewChange(null)
    }
  }, [appearanceRevision, onPreviewChange, profile.elfieId])

  function pointerDown(event: React.PointerEvent<HTMLDivElement>): void {
    if (status !== "ready") return
    pointerRef.current = { id: event.pointerId, x: event.clientX, y: event.clientY }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function pointerMove(event: React.PointerEvent<HTMLDivElement>): void {
    const previous = pointerRef.current
    if (status !== "ready" || previous?.id !== event.pointerId) return
    pointerRef.current = { id: event.pointerId, x: event.clientX, y: event.clientY }
    sendCommand("orbit", {
      delta: {
        x: clamp(event.clientX - previous.x, -35, 35) * -0.01,
        y: clamp(event.clientY - previous.y, -35, 35) * 0.01,
      },
    })
  }

  function pointerEnd(event: React.PointerEvent<HTMLDivElement>): void {
    if (pointerRef.current?.id === event.pointerId) pointerRef.current = null
  }

  function keyDown(event: React.KeyboardEvent<HTMLDivElement>): void {
    const deltas: Readonly<Record<string, Readonly<{ readonly x: number; readonly y: number }>>> = {
      ArrowLeft: { x: 0.28, y: 0 },
      ArrowRight: { x: -0.28, y: 0 },
      ArrowUp: { x: 0, y: -0.18 },
      ArrowDown: { x: 0, y: 0.18 },
    }
    const delta = deltas[event.key]
    if (delta !== undefined) {
      event.preventDefault()
      sendCommand("orbit", { delta })
      return
    }
    if (event.key === "Home") {
      event.preventDefault()
      sendCommand("reset")
      return
    }
    if (event.key === "+" || event.key === "=") {
      event.preventDefault()
      sendCommand("zoom", { delta: -0.18 })
      return
    }
    if (event.key === "-" || event.key === "_") {
      event.preventDefault()
      sendCommand("zoom", { delta: 0.18 })
    }
  }

  function sendCommand(action: string, payload: Readonly<Record<string, unknown>> = {}): void {
    try {
      const preview = previewRef.current
      if (preview === null) throw new ProfileGodotPreviewError("preview_not_ready")
      preview.send(action, payload)
    } catch (reason) {
      reportPreviewError(reason, setStatus, setError, t("profile.appearance.error"))
    }
  }

  const stageLabel = t("profile.appearance.stage", { name: profile.name })
  const statusLabel = status === "ready"
    ? t("profile.appearance.ready")
    : status === "unavailable"
      ? t("profile.appearance.unavailable")
      : status === "error"
        ? error
        : t("profile.appearance.loading")

  return (
    <div
      aria-label={stageLabel}
      className={`profile-appearance__stage${status === "ready" ? " profile-appearance__stage--ready" : ""}`}
      onKeyDown={keyDown}
      onLostPointerCapture={pointerEnd}
      onPointerCancel={pointerEnd}
      onPointerDown={pointerDown}
      onPointerMove={pointerMove}
      onPointerUp={pointerEnd}
      onWheel={(event) => {
        if (status === "ready") sendCommand("zoom", { delta: clamp(event.deltaY / 500, -0.5, 0.5) })
      }}
      ref={onStageChange}
      role="application"
      tabIndex={status === "ready" ? 0 : -1}
    >
      <iframe
        className="profile-appearance__frame"
        ref={frameRef}
        src={PROFILE_GODOT_PREVIEW_URL}
        title={stageLabel}
      />
      <div aria-hidden="true" className="profile-appearance__interaction-layer" />
      <p aria-live="polite" className="profile-appearance__status" role="status">{statusLabel}</p>
      {status === "ready" && <p className="profile-appearance__hint">{t("profile.appearance.activeHint")}</p>}
    </div>
  )
}

function previewRevision(profile: PublicProfile): number {
  const source = JSON.stringify({ appearance: profile.runtimeAppearance, species: profile.speciesId })
  let hash = 2166136261
  for (const character of source) {
    hash ^= character.charCodeAt(0)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

function reportPreviewError(
  reason: unknown,
  setStatus: (status: PreviewStatus) => void,
  setError: (message: string) => void,
  message: string,
): void {
  if (reason instanceof ProfileGodotPreviewError) {
    setStatus("error")
    setError(message)
    return
  }
  throw reason
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, Number.isFinite(value) ? value : 0))
}
