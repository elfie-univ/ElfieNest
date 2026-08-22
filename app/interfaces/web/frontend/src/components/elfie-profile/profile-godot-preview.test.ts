import { describe, expect, it, vi } from "vitest"

import {
  calculateVisibleFrameBounds,
  calculateVisibleFrameMetrics,
  createProfileGodotPreview,
  toGodotVisibleFrameMetrics,
  type ProfileGodotPreviewEvent,
} from "./profile-godot-preview"

describe("profile Godot preview bridge", () => {
  it("normalizes the visible silhouette against the rendered frame", () => {
    const width = 10
    const height = 20
    const pixels = new Uint8ClampedArray(width * height * 4)
    for (let index = 0; index < pixels.length; index += 4) {
      pixels[index] = 187
      pixels[index + 1] = 199
      pixels[index + 2] = 206
      pixels[index + 3] = 255
    }
    for (let y = 4; y <= 15; y += 1) {
      for (let x = 3; x <= 6; x += 1) {
        const offset = (y * width + x) * 4
        pixels[offset] = 80
        pixels[offset + 1] = 80
        pixels[offset + 2] = 80
      }
    }

    expect(calculateVisibleFrameMetrics(width, height, pixels)).toEqual({
      centerX: 0,
      centerY: 0,
      spanX: 0.8,
      spanY: 1.2,
    })
    expect(calculateVisibleFrameBounds(width, height, pixels)).toEqual({
      bottom: 15,
      left: 3,
      right: 6,
      top: 4,
    })
  })

  it("does not calibrate a silhouette that is already clipped by the frame", () => {
    const width = 10
    const height = 20
    const pixels = new Uint8ClampedArray(width * height * 4)
    for (let index = 0; index < pixels.length; index += 4) {
      pixels[index] = 187
      pixels[index + 1] = 199
      pixels[index + 2] = 206
      pixels[index + 3] = 255
    }
    for (let y = 6; y < height; y += 1) {
      for (let x = 3; x <= 6; x += 1) {
        const offset = (y * width + x) * 4
        pixels[offset] = 80
        pixels[offset + 1] = 80
        pixels[offset + 2] = 80
      }
    }

    expect(calculateVisibleFrameMetrics(width, height, pixels)).toBeNull()
    expect(calculateVisibleFrameBounds(width, height, pixels)).toEqual({
      bottom: height - 1,
      left: 3,
      right: 6,
      top: 6,
    })
  })

  it("serializes visible-frame metrics with the Godot wire keys", () => {
    expect(toGodotVisibleFrameMetrics({ centerX: 0.1, centerY: -0.2, spanX: 0.8, spanY: 1.6 })).toEqual({
      center_x: 0.1,
      center_y: -0.2,
      span_x: 0.8,
      span_y: 1.6,
    })
  })

  it("accepts Godot's JSON-encoded ready event", () => {
    const frame = document.createElement("iframe")
    document.body.appendChild(frame)
    if (frame.contentWindow === null) throw new TypeError("Expected the Godot frame window")
    const events: ProfileGodotPreviewEvent[] = []
    const preview = createProfileGodotPreview({ frame, onEvent: (event) => events.push(event) })

    window.dispatchEvent(new MessageEvent("message", {
      data: JSON.stringify({ channel: "elfie-lab", event: "ready" }),
      origin: window.location.origin,
      source: frame.contentWindow,
    }))

    expect(events).toEqual([{ kind: "ready" }])
    preview.dispose()
    frame.remove()
  })

  it("replays a ready flag when the Web export announced before the listener attached", async () => {
    const frame = document.createElement("iframe")
    document.body.appendChild(frame)
    if (frame.contentWindow === null) throw new TypeError("Expected the Godot frame window")
    Object.defineProperty(frame.contentWindow, "__elfieLabReady", { configurable: true, value: true })
    const events: ProfileGodotPreviewEvent[] = []
    vi.useFakeTimers()
    try {
      const preview = createProfileGodotPreview({ frame, onEvent: (event) => events.push(event) })
      await vi.advanceTimersByTimeAsync(100)
      expect(events).toEqual([{ kind: "ready" }])
      preview.dispose()
    } finally {
      vi.useRealTimers()
      frame.remove()
    }
  })

  it("turns Godot's captured data URL into the existing capture contract", async () => {
    const frame = document.createElement("iframe")
    document.body.appendChild(frame)
    if (frame.contentWindow === null) throw new TypeError("Expected the Godot frame window")
    const enqueue = vi.fn<(payload: string) => void>()
    Object.defineProperty(frame.contentWindow, "elfieLabEnqueue", { configurable: true, value: enqueue })
    const createObjectUrl = vi.fn(() => "blob:godot-capture")
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectUrl })
    const events: ProfileGodotPreviewEvent[] = []
    const preview = createProfileGodotPreview({ frame, onEvent: (event) => events.push(event) })

    const capturePromise = preview.capture()
    const command = JSON.parse(String(enqueue.mock.calls[0]?.[0]))
    const requestId = String(command.request_id)
    window.dispatchEvent(new MessageEvent("message", {
      data: {
        channel: "elfie-lab",
        data_url: `data:image/png;base64,${btoa("png")}`,
        event: "portrait",
        request_id: requestId,
      },
      origin: window.location.origin,
      source: frame.contentWindow,
    }))

    const capture = await capturePromise
    expect(capture.blob.type).toBe("image/png")
    expect(await capture.blob.text()).toBe("png")
    expect(capture.previewUrl).toBe("blob:godot-capture")
    expect(createObjectUrl).toHaveBeenCalledWith(capture.blob)
    expect(events).toEqual([])

    preview.dispose()
    frame.remove()
    Reflect.deleteProperty(URL, "createObjectURL")
  })

  it("falls back to a same-origin message when the Web export has no enqueue function", () => {
    const frame = document.createElement("iframe")
    document.body.appendChild(frame)
    if (frame.contentWindow === null) throw new TypeError("Expected the Godot frame window")
    const postMessage = vi.spyOn(frame.contentWindow, "postMessage")
    const preview = createProfileGodotPreview({ frame, onEvent: () => undefined })

    preview.send("reset")

    expect(postMessage).toHaveBeenCalledOnce()
    const [encoded, origin] = postMessage.mock.calls[0] ?? []
    expect(origin).toBe(window.location.origin)
    expect(JSON.parse(String(encoded))).toMatchObject({
      action: "reset",
      channel: "elfie-lab",
    })

    preview.dispose()
    frame.remove()
  })

  it("waits for a Godot action completion before continuing", async () => {
    const frame = document.createElement("iframe")
    document.body.appendChild(frame)
    if (frame.contentWindow === null) throw new TypeError("Expected the Godot frame window")
    const enqueue = vi.fn<(payload: string) => void>()
    Object.defineProperty(frame.contentWindow, "elfieLabEnqueue", { configurable: true, value: enqueue })
    const preview = createProfileGodotPreview({ frame, onEvent: () => undefined })

    const resetPromise = preview.sendAndWait("reset")
    const command = JSON.parse(String(enqueue.mock.calls[0]?.[0]))
    const requestId = String(command.request_id)
    let settled = false
    void resetPromise.then(() => { settled = true })
    await Promise.resolve()
    expect(settled).toBe(false)

    window.dispatchEvent(new MessageEvent("message", {
      data: { action: "reset", channel: "elfie-lab", event: "completed", request_id: requestId },
      origin: window.location.origin,
      source: frame.contentWindow,
    }))
    await resetPromise
    expect(settled).toBe(true)

    preview.dispose()
    frame.remove()
  })
})
