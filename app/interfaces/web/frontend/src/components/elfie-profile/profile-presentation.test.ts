import { describe, expect, it } from "vitest"

import type { ElfieProfile } from "../../api/client"
import { presentElfieProfile } from "./profile-presentation"

const REAL_API_PROFILE = {
  appearance: {},
  big_five: {},
  birth_date: null,
  elfie_id: "elfie_default",
  embodiment: { state: "at_nest" },
  gender: null,
  name: "Mochi",
  nest: { bed_name: null, posture: "resting", room_name: null },
  online_status: "online",
  personality_tags: [],
  portrait_url: "",
  species_id: "fox",
  status: { code: "awake", label: "在线", tone: "active" },
  summary: "喜欢守在门边等熟悉的脚步声。",
} satisfies ElfieProfile

describe("presentElfieProfile", () => {
  it("projects a real API profile as adopter only when the known adopter matches", () => {
    // Given: a real API Elfie whose ChatData adopter is the signed-in account.
    const projection = presentElfieProfile(REAL_API_PROFILE, "account-a", "account-a")

    // When: the presentation boundary resolves ownership.
    if (projection === null || projection.kind !== "adopter") {
      throw new TypeError("Expected an adopter projection")
    }

    // Then: the safe real-data projection has six empty modules and no fixture data.
    expect(projection.publicProfile.name).toBe("Mochi")
    expect(projection.privateCognition.modules).toHaveLength(6)
    expect(JSON.stringify(projection.privateCognition)).not.toMatch(/Happy|Kettle|admin123|user123/)
  })

  it("projects the same real API profile as visitor when the known adopter differs", () => {
    // Given: the same real API Elfie viewed by a different account.
    const projection = presentElfieProfile(REAL_API_PROFILE, "account-b", "account-a")

    // When: the presentation boundary resolves ownership.
    if (projection === null) throw new TypeError("Expected a visitor projection")

    // Then: private cognition is omitted rather than returned empty to the visitor.
    expect(projection.kind).toBe("visitor")
    expect(Object.keys(projection)).toEqual(["kind", "ownerDisplayName", "publicProfile"])
  })
})
