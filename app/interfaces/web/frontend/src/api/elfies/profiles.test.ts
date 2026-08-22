import { describe, expect, it, vi } from "vitest"

import { requestJson } from "../http"
import { elfiePortraitUrl, elfies, profile, saveElfiePortrait } from "./profiles"

vi.mock("../http", () => ({
  csrfHeaders: (csrfToken: string) => ({ "X-CSRF-Token": csrfToken }),
  requestJson: vi.fn(),
}))

describe("member Elfies client", () => {
  it("builds an encoded portrait URL for each supported framing", () => {
    expect(elfiePortraitUrl("elfie/one", "full_body")).toBe("/api/v1/elfies/elfie%2Fone/portrait?kind=full_body")
    expect(elfiePortraitUrl("elfie/one")).toBe("/api/v1/elfies/elfie%2Fone/portrait?kind=headshot")
  })

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
    }, {
      relationship: "other",
      permissions: { can_view_profile: true, can_view_cognition: false },
      profile: {
        elfie_id: "00000002", name: "Kettle", species_id: "dog", gender: null,
        birth_date: null, summary: null, adopted_at: "2026-08-02",
        profile_status: "empty", big_five: null, personality_tags: [],
        portrait_url: "", appearance: null,
      },
    }] })

    const profiles = await elfies()

    expect(profiles[0]?.name).toBe("Mochi")
    expect(profiles[0]?.relationship).toBe("owned")
    expect(profiles[1]?.relationship).toBe("other")
    expect(profiles[0]).not.toHaveProperty("food_policy")
    expect(profiles[0]).not.toHaveProperty("nest")
    expect(profiles[0]).not.toHaveProperty("embodiment")
  })

  it("accepts a public profile without private cognition", async () => {
    vi.mocked(requestJson).mockResolvedValue({
      relationship: "other",
      permissions: { can_view_profile: true, can_view_cognition: false },
      profile: {
        elfie_id: "00000002", name: "Kettle", species_id: "dog", gender: null,
        birth_date: null, summary: null, adopted_at: "2026-08-02",
        profile_status: "empty", big_five: null, personality_tags: [],
        portrait_url: "", appearance: null,
      },
      private_cognition: null,
    })

    const result = await profile("00000002")

    expect(result.name).toBe("Kettle")
    expect(result.relationship).toBe("other")
    expect(result.private_cognition).toBeNull()
  })

  it("uploads the selected PNG with the session CSRF token", async () => {
    vi.mocked(requestJson).mockClear()
    vi.mocked(requestJson).mockResolvedValue({
      portrait_url: "/api/v1/elfies/00000001/portrait",
    })
    const image = new Blob(["png"], { type: "image/png" })

    await expect(saveElfiePortrait("elfie/one", image, "csrf-token")).resolves.toBe(
      "/api/v1/elfies/00000001/portrait",
    )

    const call = vi.mocked(requestJson).mock.calls[0]
    expect(call?.[0]).toBe("/api/v1/elfies/elfie%2Fone/portrait")
    const init = call?.[1]
    expect(init?.method).toBe("PUT")
    expect(init?.headers).toEqual({ "X-CSRF-Token": "csrf-token" })
    expect(init?.body).toBeInstanceOf(FormData)
    expect((init?.body as FormData).get("file")).toBeInstanceOf(File)
  })
})
