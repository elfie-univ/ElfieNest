import { describe, expect, it, vi } from "vitest"

import {
  createProfileGodotPreview,
  type ProfileGodotPreviewEvent,
} from "./profile-godot-preview"

describe("profile Godot preview bridge", () => {
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
})
