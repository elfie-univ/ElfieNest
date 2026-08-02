import { describe, expect, it } from "vitest"

import { parseChatSocketEvent } from "./chat-socket"

describe("parseChatSocketEvent", () => {
  it("accepts the canonical account principal in the ready event", () => {
    const event = parseChatSocketEvent({ event: "ready", principal: { role: "owner", account_id: "owner" } })
    expect(event).toEqual({ event: "ready", principal: { role: "owner", account_id: "owner" } })
  })

  it("accepts the typed message acknowledgement emitted by the Core", () => {
    const event = parseChatSocketEvent({
      event: "message",
      message: { id: 7, elfie_id: "00000001", sender: "user", text: "你好", created_at: "2026-07-24T08:00:00Z" }
    })
    expect(event).toMatchObject({ event: "message", message: { elfie_id: "00000001" } })
  })

  it("rejects an untyped WebSocket payload before it reaches the page", () => {
    expect(() => parseChatSocketEvent({ event: "message", message: { text: "缺少字段" } })).toThrow()
  })

  it("preserves an unknown backend error payload as protocol data", () => {
    // Given: the server sends an error detail unknown to the UI.
    const payload = { event: "error", detail: "upstream-private-detail-123" }

    // When: the WebSocket boundary parses the payload.
    const event = parseChatSocketEvent(payload)

    // Then: protocol data remains unchanged for the localized-error boundary to handle.
    expect(event).toEqual(payload)
  })

  it("rejects malformed error payloads before localized UI handling", () => {
    // Given: an error event has no typed string detail.
    const payload = { event: "error", detail: { nested: "not-a-string" } }

    // When/Then: parsing fails at the WebSocket boundary.
    expect(() => parseChatSocketEvent(payload)).toThrow()
  })
})
