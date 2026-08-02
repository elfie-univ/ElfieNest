import { beforeEach, describe, expect, it, vi } from "vitest"

import { ownerElfies } from "./owner-elfies"
import { requestJson } from "./http"

vi.mock("./http", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("./http")>()
  return { ...original, requestJson: vi.fn() }
})

describe("owner Elfie API boundary", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("normalizes the current backend profile into the UI status contract", async () => {
    // Given: the backend projection contains online/embodiment fields but no derived status object.
    vi.mocked(requestJson).mockResolvedValue([{
      elfie_id: "36517482",
      owner: { user_id: 1, account_id: "admin123", display_name: "lz" },
      profile: {
        elfie_id: "36517482",
        name: "星尘",
        species_id: "dog",
        gender: null,
        birth_date: null,
        summary: "好奇探索",
        online_status: "unknown",
        portrait_url: "",
        appearance: {},
        big_five: {},
        personality_tags: ["好奇探索"],
        nest: {
          room_id: null,
          room_name: null,
          bed_id: null,
          bed_name: null,
          posture: "unknown",
        },
        embodiment: { state: "at_nest" },
      },
      food_policy: {
        main_food_id: "",
        effective_main_food_id: "",
        main_food_options: [],
        main_food_unavailable: false,
      },
      created_at: "2026-08-02T02:16:57.443166+00:00",
    }])

    // When: the real owner payload crosses the API boundary.
    const [elfie] = await ownerElfies()

    // Then: the UI receives a typed status without losing backend identity data.
    expect(elfie?.profile.status).toEqual({ code: "at_nest", label: "at_nest", tone: "active" })
    expect(elfie?.profile.name).toBe("星尘")
  })
})
