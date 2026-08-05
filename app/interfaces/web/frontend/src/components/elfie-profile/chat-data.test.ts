import { describe, expect, it } from "vitest"

import { createOwnedChatData } from "./chat-data"

describe("chat history data", () => {
  it("keeps only conversation summaries with a real message timestamp", () => {
    const data = createOwnedChatData(
      [],
      [
        { elfie_id: "00000001", name: "小羽", portrait_url: "", last_message_preview: "", last_message_at: null },
        { elfie_id: "00000002", name: "阿栗", portrait_url: "", last_message_preview: "你好", last_message_at: "2026-08-05T01:02:03Z" },
      ],
      "owner",
    )

    expect(data.conversations).toEqual([
      { elfie_id: "00000002", name: "阿栗", portrait_url: "", last_message_preview: "你好", last_message_at: "2026-08-05T01:02:03Z" },
    ])
  })
})
