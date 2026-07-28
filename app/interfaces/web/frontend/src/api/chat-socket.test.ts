import { describe, expect, it } from "vitest"

import { parseChatSocketEvent } from "./chat-socket"

describe("parseChatSocketEvent", () => {
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
})
