import { describe, expect, it, vi } from "vitest"

import { requestJson } from "../http"
import { elfies } from "./profiles"

vi.mock("../http", () => ({ requestJson: vi.fn() }))

describe("member Elfies client", () => {
  it("unwraps the strict visible collection without adjacent-domain facts", async () => {
    vi.mocked(requestJson).mockResolvedValue({ items: [{
      relationship: "owned",
      permissions: { can_view_profile: true, can_view_cognition: true },
      profile: {
        elfie_id: "00000001", name: "Mochi", species_id: "fox", gender: null,
        birth_date: null, summary: null, adopted_at: "2026-08-01",
        profile_status: "empty", big_five: null, personality_tags: [],
        portrait_url: "", appearance: null,
      },
    }] })

    const [profile] = await elfies()

    expect(profile?.name).toBe("Mochi")
    expect(profile).not.toHaveProperty("food_policy")
    expect(profile).not.toHaveProperty("nest")
    expect(profile).not.toHaveProperty("embodiment")
  })
})
