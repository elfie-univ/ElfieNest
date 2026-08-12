import { describe, expect, it } from "vitest"

import { ChatMessageSchema, ConversationSchema } from "./communication"

describe("communication API schemas", () => {
  it("accepts stable non-numeric Elfie ids", () => {
    expect(ChatMessageSchema.parse({
      id: 1,
      elfie_id: "elfie_default",
      sender: "elfie",
      text: "你好",
      created_at: "2026-07-28T00:00:00Z",
    }).elfie_id).toBe("elfie_default")
  })

  it("rejects fields outside the strict conversation contract", () => {
    expect(ConversationSchema.safeParse({
      elfie_id: "elfie_default",
      name: "小白",
      portrait_url: "",
      last_message_preview: "你好",
      last_message_at: "2026-07-28T00:00:00Z",
      page_only_hint: true,
    }).success).toBe(false)
  })
})
