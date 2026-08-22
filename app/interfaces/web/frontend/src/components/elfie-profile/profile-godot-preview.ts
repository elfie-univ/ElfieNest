import { z } from "zod"

import type { AppearanceCapture } from "./appearance-capture"

const GodotPreviewMessageSchema = z.object({
  channel: z.literal("elfie-lab"),
  event: z.string(),
  action: z.string().optional(),
  request_id: z.string().optional(),
  data_url: z.string().optional(),
  reason: z.string().optional(),
})

type GodotPreviewMessage = z.infer<typeof GodotPreviewMessageSchema>
type PreviewPayload = Readonly<Record<string, unknown>>

export type VisibleFrameMetrics = {
  readonly centerX: number
  readonly centerY: number
  readonly spanX: number
  readonly spanY: number
}

export type VisibleFrameBounds = {
  readonly left: number
  readonly top: number
  readonly right: number
  readonly bottom: number
}

/** Converts the browser-side metrics into the snake_case payload used by Godot. */
export function toGodotVisibleFrameMetrics(metrics: VisibleFrameMetrics): Readonly<Record<string, number>> {
  return {
    center_x: metrics.centerX,
    center_y: metrics.centerY,
    span_x: metrics.spanX,
    span_y: metrics.spanY,
  }
}

const VISIBLE_PIXEL_THRESHOLD = 18

export type ProfileGodotPreviewEvent =
  | { readonly kind: "ready" }
  | { readonly action: string; readonly kind: "completed"; readonly requestId: string }
  | { readonly action: string; readonly kind: "unsupported"; readonly reason: string; readonly requestId: string }

export type ProfileGodotPreview = {
  readonly capture: () => Promise<AppearanceCapture>
  readonly dispose: () => void
  readonly send: (action: string, payload?: PreviewPayload) => void
  readonly sendAndWait: (action: string, payload?: PreviewPayload) => Promise<void>
}

export class ProfileGodotPreviewError extends Error {
  public readonly name = "ProfileGodotPreviewError"

  public constructor(public readonly reason: string) {
    super(reason)
  }
}

/**
 * Finds the non-background silhouette in a rendered Godot frame.
 * centerY is positive when the silhouette is above the frame center, matching
 * the camera-focus correction expected by lab_preview_controller.gd.
 */
export function calculateVisibleFrameMetrics(
  width: number,
  height: number,
  pixels: Uint8ClampedArray,
): VisibleFrameMetrics | null {
  const bounds = calculateVisibleFrameBounds(width, height, pixels)
  if (bounds === null) return null

  // A silhouette touching the canvas edge is clipped. Its measured height is
  // therefore smaller than the real model height; sending that value back to
  // Godot would zoom in again and make the clipping worse. Let the geometry
  // fit remain authoritative until a complete frame is available.
  if (bounds.left <= 0 || bounds.top <= 0 || bounds.right >= width - 1 || bounds.bottom >= height - 1) {
    return null
  }

  const visibleWidth = bounds.right - bounds.left + 1
  const visibleHeight = bounds.bottom - bounds.top + 1
  return {
    centerX: ((bounds.left + bounds.right + 1) / width - 1) * 1,
    centerY: (1 - (bounds.top + bounds.bottom + 1) / height) * 1,
    spanX: (visibleWidth / width) * 2,
    spanY: (visibleHeight / height) * 2,
  }
}

export function calculateVisibleFrameBounds(
  width: number,
  height: number,
  pixels: Uint8ClampedArray,
): VisibleFrameBounds | null {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 2 || height < 2) return null
  if (pixels.length < width * height * 4) return null

  const background = sampleBackground(width, height, pixels)
  let left = width
  let right = -1
  let top = height
  let bottom = -1
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const offset = (y * width + x) * 4
      if ((pixels[offset + 3] ?? 0) < 8) continue
      const difference = Math.max(
        Math.abs((pixels[offset] ?? 0) - background[0]),
        Math.abs((pixels[offset + 1] ?? 0) - background[1]),
        Math.abs((pixels[offset + 2] ?? 0) - background[2]),
      )
      if (difference <= VISIBLE_PIXEL_THRESHOLD) continue
      left = Math.min(left, x)
      right = Math.max(right, x)
      top = Math.min(top, y)
      bottom = Math.max(bottom, y)
    }
  }
  if (right < left || bottom < top) return null

  const visibleWidth = right - left + 1
  const visibleHeight = bottom - top + 1
  if (visibleWidth < 2 || visibleHeight < 2) return null
  return { bottom, left, right, top }
}

export async function measureVisibleFrame(blob: Blob): Promise<VisibleFrameMetrics | null> {
  if (typeof URL.createObjectURL !== "function") return null
  let sourceUrl: string | undefined
  try {
    sourceUrl = URL.createObjectURL(blob)
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const element = new Image()
      element.onload = () => resolve(element)
      element.onerror = () => reject(new ProfileGodotPreviewError("invalid_portrait"))
      element.src = sourceUrl as string
    })
    const width = image.naturalWidth
    const height = image.naturalHeight
    if (width < 2 || height < 2) return null
    const canvas = document.createElement("canvas")
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext("2d")
    if (context === null) return null
    context.drawImage(image, 0, 0, width, height)
    return calculateVisibleFrameMetrics(width, height, context.getImageData(0, 0, width, height).data)
  } catch {
    return null
  } finally {
    if (sourceUrl !== undefined && typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(sourceUrl)
  }
}

function sampleBackground(width: number, height: number, pixels: Uint8ClampedArray): readonly [number, number, number] {
  const samples = [
    0,
    (width - 1) * 4,
    ((height - 1) * width) * 4,
    ((height - 1) * width + width - 1) * 4,
  ]
  let red = 0
  let green = 0
  let blue = 0
  for (const offset of samples) {
    red += pixels[offset] ?? 0
    green += pixels[offset + 1] ?? 0
    blue += pixels[offset + 2] ?? 0
  }
  return [red / samples.length, green / samples.length, blue / samples.length]
}

type PendingCapture = {
  readonly reject: (error: ProfileGodotPreviewError) => void
  readonly resolve: (capture: AppearanceCapture) => void
}

type PendingAction = {
  readonly reject: (error: ProfileGodotPreviewError) => void
  readonly resolve: () => void
}

type ProfileGodotPreviewOptions = {
  readonly frame: HTMLIFrameElement
  readonly onEvent: (event: ProfileGodotPreviewEvent) => void
}

let requestSequence = 0

export function createProfileGodotPreview({ frame, onEvent }: ProfileGodotPreviewOptions): ProfileGodotPreview {
  const pendingCaptures = new Map<string, PendingCapture>()
  const pendingActions = new Map<string, PendingAction>()
  let readyNotified = false
  let readyPollTimer: number | undefined

  function notifyReady(): void {
    if (readyNotified) return
    readyNotified = true
    if (readyPollTimer !== undefined) {
      window.clearInterval(readyPollTimer)
      readyPollTimer = undefined
    }
    onEvent({ kind: "ready" })
  }

  function pollReadyFlag(): void {
    try {
      if (frame.contentWindow?.__elfieLabReady === true) notifyReady()
    } catch {
      // The iframe may still be transitioning into its same-origin document.
    }
  }

  function sendWithId(requestId: string, action: string, payload: PreviewPayload): void {
    const receiver = frame.contentWindow?.elfieLabEnqueue
    const encoded = JSON.stringify({
      channel: "elfie-lab",
      action,
      request_id: requestId,
      payload,
    })
    if (receiver !== undefined) {
      receiver(encoded)
      return
    }
    const target = frame.contentWindow
    if (target === null) {
      throw new ProfileGodotPreviewError("preview_not_ready")
    }
    target.postMessage(encoded, window.location.origin)
  }

  function send(action: string, payload: PreviewPayload = {}): void {
    sendWithId(nextRequestId(), action, payload)
  }

  function sendAndWait(action: string, payload: PreviewPayload = {}): Promise<void> {
    const requestId = nextRequestId()
    return new Promise<void>((resolve, reject) => {
      pendingActions.set(requestId, { reject, resolve })
      try {
        sendWithId(requestId, action, payload)
      } catch (error) {
        pendingActions.delete(requestId)
        reject(error instanceof ProfileGodotPreviewError
          ? error
          : new ProfileGodotPreviewError("preview_send_failed"))
      }
    })
  }

  function capture(): Promise<AppearanceCapture> {
    const requestId = nextRequestId()
    return new Promise<AppearanceCapture>((resolve, reject) => {
      pendingCaptures.set(requestId, { reject, resolve })
      try {
        sendWithId(requestId, "capture", {})
      } catch (error) {
        pendingCaptures.delete(requestId)
        if (error instanceof ProfileGodotPreviewError) {
          reject(error)
          return
        }
        throw error
      }
    })
  }

  function onMessage(event: MessageEvent<unknown>): void {
    if (event.origin !== window.location.origin || event.source !== frame.contentWindow) {
      return
    }
    const parsed = GodotPreviewMessageSchema.safeParse(decodePreviewMessage(event.data))
    if (!parsed.success) return
    handleMessage(parsed.data)
  }

  function handleMessage(message: GodotPreviewMessage): void {
    if (message.event === "ready") {
      notifyReady()
      return
    }
    if (message.event === "portrait") {
      const requestId = message.request_id
      if (requestId === undefined || message.data_url === undefined) return
      const pending = pendingCaptures.get(requestId)
      if (pending === undefined) return
      pendingCaptures.delete(requestId)
      try {
        pending.resolve(captureFromDataUrl(message.data_url))
      } catch (error) {
        if (error instanceof ProfileGodotPreviewError) {
          pending.reject(error)
          return
        }
        throw error
      }
      return
    }
    const requestId = message.request_id
    const action = message.action
    if (requestId === undefined || action === undefined) return
    if (message.event === "completed") {
      const pendingAction = pendingActions.get(requestId)
      if (pendingAction !== undefined) {
        pendingActions.delete(requestId)
        pendingAction.resolve()
      }
      onEvent({ action, kind: "completed", requestId })
      return
    }
    if (message.event === "unsupported") {
      const pendingAction = pendingActions.get(requestId)
      if (pendingAction !== undefined) {
        pendingActions.delete(requestId)
        pendingAction.reject(new ProfileGodotPreviewError(message.reason ?? "preview_action_unsupported"))
      }
      const pending = pendingCaptures.get(requestId)
      if (pending !== undefined) {
        pendingCaptures.delete(requestId)
        pending.reject(new ProfileGodotPreviewError(message.reason ?? "preview_action_unsupported"))
      }
      onEvent({ action, kind: "unsupported", reason: message.reason ?? "unsupported", requestId })
      return
    }
  }

  function dispose(): void {
    window.removeEventListener("message", onMessage)
    if (readyPollTimer !== undefined) {
      window.clearInterval(readyPollTimer)
      readyPollTimer = undefined
    }
    const error = new ProfileGodotPreviewError("preview_closed")
    for (const pending of pendingActions.values()) pending.reject(error)
    pendingActions.clear()
    for (const pending of pendingCaptures.values()) pending.reject(error)
    pendingCaptures.clear()
  }

  window.addEventListener("message", onMessage)
  readyPollTimer = window.setInterval(pollReadyFlag, 100)
  pollReadyFlag()
  return { capture, dispose, send, sendAndWait }
}

function nextRequestId(): string {
  requestSequence += 1
  const randomId = globalThis.crypto?.randomUUID?.()
  return randomId === undefined ? `profile-preview-${Date.now()}-${requestSequence}` : randomId
}

function decodePreviewMessage(input: unknown): unknown {
  if (typeof input !== "string") return input
  try {
    return JSON.parse(input)
  } catch {
    return null
  }
}

function captureFromDataUrl(dataUrl: string): AppearanceCapture {
  const match = /^data:([^;,]+);base64,(.+)$/.exec(dataUrl)
  const mediaType = match?.[1]
  const encoded = match?.[2]
  if (mediaType === undefined || encoded === undefined) {
    throw new ProfileGodotPreviewError("invalid_portrait")
  }
  const binary = atob(encoded)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  const blob = new Blob([bytes], { type: mediaType })
  if (typeof URL.createObjectURL !== "function") {
    throw new ProfileGodotPreviewError("invalid_portrait")
  }
  return { blob, previewUrl: URL.createObjectURL(blob) }
}

declare global {
  interface Window {
    __elfieLabReady?: boolean
    elfieLabEnqueue?: (payload: string) => void
  }
}
