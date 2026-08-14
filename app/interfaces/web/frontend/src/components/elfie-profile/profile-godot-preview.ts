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

export type ProfileGodotPreviewEvent =
  | { readonly kind: "ready" }
  | { readonly action: string; readonly kind: "completed"; readonly requestId: string }
  | { readonly action: string; readonly kind: "unsupported"; readonly reason: string; readonly requestId: string }

export type ProfileGodotPreview = {
  readonly capture: () => Promise<AppearanceCapture>
  readonly dispose: () => void
  readonly send: (action: string, payload?: PreviewPayload) => void
}

export class ProfileGodotPreviewError extends Error {
  public readonly name = "ProfileGodotPreviewError"

  public constructor(public readonly reason: string) {
    super(reason)
  }
}

type PendingCapture = {
  readonly reject: (error: ProfileGodotPreviewError) => void
  readonly resolve: (capture: AppearanceCapture) => void
}

type ProfileGodotPreviewOptions = {
  readonly frame: HTMLIFrameElement
  readonly onEvent: (event: ProfileGodotPreviewEvent) => void
}

let requestSequence = 0

export function createProfileGodotPreview({ frame, onEvent }: ProfileGodotPreviewOptions): ProfileGodotPreview {
  const pendingCaptures = new Map<string, PendingCapture>()
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
      onEvent({ action, kind: "completed", requestId })
      return
    }
    if (message.event === "unsupported") {
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
    for (const pending of pendingCaptures.values()) pending.reject(error)
    pendingCaptures.clear()
  }

  window.addEventListener("message", onMessage)
  readyPollTimer = window.setInterval(pollReadyFlag, 100)
  pollReadyFlag()
  return { capture, dispose, send }
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
  return { blob, previewUrl: URL.createObjectURL(blob) }
}

declare global {
  interface Window {
    __elfieLabReady?: boolean
    elfieLabEnqueue?: (payload: string) => void
  }
}
