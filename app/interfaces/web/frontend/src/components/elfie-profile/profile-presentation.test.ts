import { describe, expect, it } from "vitest"

import type { ElfieProfileDetail } from "../../api/client"
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
  private_cognition: {
    status: "ready" as const,
    recent_focus: { topics: [{ id: "topic:门边", label: "门边", category: "place", weight: 1 }] },
    important_experiences: { entries: [] },
    relationship_world: {
      nodes: [{ id: "self", label: "Mochi", kind: "self" as const, weight: 1 }],
      edges: [],
    },
    world_understanding: {
      summary: "安静的地方让我放松。",
      rings: [
        { key: "self" as const, nodes: [] },
        { key: "family" as const, nodes: [] },
        { key: "nest" as const, nodes: [] },
        { key: "society" as const, nodes: [] },
        { key: "outside" as const, nodes: [] },
      ],
    },
    knowledge_beliefs: { nodes: [], edges: [] },
  },
  care_settings: {
    food: { selected_id: "", selected_label: "", options: [], unavailable: false },
  },
} satisfies ElfieProfileDetail

describe("presentElfieProfile", () => {
  it("projects a real API profile as adopter only when the known adopter matches", () => {
    // Given: a real API Elfie whose ChatData adopter is the signed-in account.
    const projection = presentElfieProfile(REAL_API_PROFILE, "account-a", "account-a")

    // When: the presentation boundary resolves ownership.
    if (projection === null || projection.kind !== "adopter") {
      throw new TypeError("Expected an adopter projection")
    }

    // Then: the real API cognition payload is mapped without falling back to a demo fixture.
    expect(projection.publicProfile.name).toBe("Mochi")
    expect(projection.privateCognition.recentFocus.topics[0]?.label).toBe("门边")
    expect(projection.privateCognition.importantExperiences.entries).toHaveLength(0)
    expect(projection.careSettings.food.selectedId).toBe("")
    expect(JSON.stringify(projection.privateCognition)).not.toMatch(/Happy|Kettle|admin123|user123/)
  })

  it("projects the same real API profile as visitor when the known adopter differs", () => {
    // Given: the same real API Elfie viewed by a different account.
    const projection = presentElfieProfile(REAL_API_PROFILE, "account-b", "account-a")

    // When: the presentation boundary resolves ownership.
    if (projection === null) throw new TypeError("Expected a visitor projection")

    // Then: private cognition is omitted rather than returned empty to the visitor.
    if (projection.kind !== "visitor") {
      throw new TypeError("Expected a visitor projection")
    }
    expect(Object.keys(projection)).toEqual(["ageLabel", "kind", "ownerDisplayName", "publicProfile"])
    expect(projection.ageLabel).toBe("未登记")
  })
})
