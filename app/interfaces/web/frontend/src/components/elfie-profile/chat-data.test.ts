import { describe, expect, it } from "vitest"

import type { ElfieProfile } from "../../api/client"
import { createOwnedChatData, presentChatText, recordChatMessage } from "./chat-data"

function testElfie(elfieId: string, name: string): ElfieProfile {
  return {
    elfie_id: elfieId,
    name,
    portrait_url: "",
    species_id: "fox",
    gender: null,
    birth_date: null,
    summary: null,
    adopted_at: "2026-08-01",
    profile_status: "empty",
    appearance: null,
    big_five: null,
    personality_tags: [],
  }
}

describe("chat history data", () => {
  it("includes every owned Elfie even before the first message", () => {
    const data = createOwnedChatData(
      [{
        elfie_id: "00000001",
        name: "小羽",
        portrait_url: "",
        species_id: "fox",
        gender: null,
        birth_date: null,
        summary: null,
        adopted_at: "2026-08-01",
        profile_status: "empty",
        appearance: null,
        big_five: null,
        personality_tags: [],
      }, {
        elfie_id: "00000002",
        name: "阿栗",
        portrait_url: "",
        species_id: "dog",
        gender: null,
        birth_date: null,
        summary: null,
        adopted_at: "2026-08-02",
        profile_status: "empty",
        appearance: null,
        big_five: null,
        personality_tags: [],
        relationship: "other",
      }],
      [
        { elfie_id: "00000001", name: "小羽", portrait_url: "", last_message_preview: "", last_message_at: null },
        { elfie_id: "00000002", name: "阿栗", portrait_url: "", last_message_preview: "你好", last_message_at: "2026-08-05T01:02:03Z" },
      ],
      "owner",
    )

    expect(data.conversations).toEqual([
      { elfie_id: "00000001", name: "小羽", portrait_url: "", last_message_preview: "", last_message_at: null },
    ])
    expect(data.adopterAccountIds["00000002"]).toBe("")
  })

  it("extracts only approved natural language from a legacy DecisionPlan wrapper", () => {
    const legacy = `\`\`\`json
{"DecisionPlan":{"actions":[{"action":"respond","parameters":{"content":"有效回复"}}]}}
\`\`\``

    expect(presentChatText(legacy)).toBe("有效回复")
    expect(presentChatText("普通文本")).toBe("普通文本")
    expect(presentChatText("普通文本 [ACTION]nod_head[/ACTION]")).toBe("普通文本")
    expect(presentChatText('{"DecisionPlan":{"actions":[]}}')).toBe("")
    expect(presentChatText('{"schema_version":1,"intents":[{"type":"speech","text":"原生回复"}]}')).toBe("原生回复")
  })

  it("keeps user-authored structured text visible", () => {
    const data = createOwnedChatData(
      [{
        elfie_id: "00000001",
        name: "小羽",
        portrait_url: "",
        species_id: "fox",
        gender: null,
        birth_date: null,
        summary: null,
        adopted_at: "2026-08-01",
        profile_status: "empty",
        appearance: null,
        big_five: null,
        personality_tags: [],
      }],
      [],
      "owner",
    )
    const userText = '{"hello":"world"}'
    const recorded = recordChatMessage(data, {
      id: 2,
      elfie_id: "00000001",
      sender: "user",
      text: userText,
      created_at: "2026-08-05T01:02:04Z",
    })

    expect(recorded.conversations[0]?.last_message_preview).toBe(userText)
  })

  it("sanitizes an initial legacy preview and preserves unknown structured previews", () => {
    const data = createOwnedChatData(
      [testElfie("00000001", "小羽"), testElfie("00000002", "阿栗")],
      [
        {
          elfie_id: "00000001",
          name: "小羽",
          portrait_url: "",
          last_message_preview: '{"DecisionPlan":{"actions":[{"action":"respond","parameters":{"text":"刷新后的回复"}}]}}',
          last_message_at: "2026-08-05T01:02:03Z",
        },
        {
          elfie_id: "00000002",
          name: "阿栗",
          portrait_url: "",
          last_message_preview: '{"hello":"world"}',
          last_message_at: "2026-08-05T01:02:04Z",
        },
      ],
      "owner",
    )

    expect(data.conversations.map((row) => row.last_message_preview)).toEqual([
      "刷新后的回复",
      '{"hello":"world"}',
    ])
  })

  it("uses the same normalized text for a live message and its conversation preview", () => {
    const data = createOwnedChatData(
      [{
        elfie_id: "00000001",
        name: "小羽",
        portrait_url: "",
        species_id: "fox",
        gender: null,
        birth_date: null,
        summary: null,
        adopted_at: "2026-08-01",
        profile_status: "empty",
        appearance: null,
        big_five: null,
        personality_tags: [],
      }],
      [],
      "owner",
    )
    const recorded = recordChatMessage(data, {
      id: 1,
      elfie_id: "00000001",
      sender: "elfie",
      text: '{"DecisionPlan":{"actions":[{"action":"respond","parameters":{"text":"只显示这句"}}]}}',
      created_at: "2026-08-05T01:02:03Z",
    })

    expect(recorded.conversations[0]?.last_message_preview).toBe("只显示这句")
  })
})
