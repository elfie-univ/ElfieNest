import { beforeEach, describe, expect, it, vi } from "vitest"

import { requestJson } from "../http"
import { adoptionCandidates, adoptionInfo, adoptionReplies, commitAdoption } from "./adoption"

vi.mock("../http", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../http")>()
  return { ...original, requestJson: vi.fn() }
})

const candidate = {
  candidate_id: "candidate-1",
  species_id: "fox",
  life_stage: "young_adult" as const,
  age_months: 36,
  gender: "male" as const,
  full_body_image_url: "",
  headshot_image_url: "",
  appearance_tags: ["高挑"],
  personality_tags: ["好奇探索"],
  runtime_appearance: { species_id: "fox" },
}

describe("versioned current-member Adoption client", () => {
  beforeEach(() => vi.clearAllMocks())

  it("uses only the current-member Adoption resource", async () => {
    vi.mocked(requestJson)
      .mockResolvedValueOnce({
        personality_styles: ["好奇探索"],
        species: [
          {
            species_id: "fox",
            canon_id: "saevi",
            display_name: "Saevi",
            display_name_zh: "灵狐",
            earth_shape_label: "fox-like",
            scene_id: "fox",
            sort_order: 0,
          },
          {
            species_id: "dog",
            canon_id: "tovren",
            display_name: "Tovren",
            display_name_zh: "灵犬",
            earth_shape_label: "dog-like",
            scene_id: "dog",
            sort_order: 1,
          },
        ],
        heights: ["standard"],
        builds: ["standard"],
        life_stages: ["any"],
        quota: { used: 0, max: 3, remaining: 3, can_adopt: true },
        nest_capacity: { used: 0, max: 4, remaining: 4 },
        availability: "available",
      })
      .mockResolvedValueOnce({ candidate_set_id: "set-1", adoption_session_id: "session-1", batch_number: 1, candidates: Array(5).fill(candidate) })
      .mockResolvedValueOnce({
        candidate_set_id: "set-1",
        replies: [{ ...candidate, status: "accepted", message: "yes", reveal: null }],
      })
      .mockResolvedValueOnce({ elfie_id: "00000001", name: "阿洛", species_id: "fox" })

    await adoptionInfo()
    await adoptionCandidates({
      species_id: "fox",
      life_stage: "any",
      gender: "any",
      appearance: {
        stature: "any",
        build: "any",
        face: "any",
        signature: "any",
        priority: "face",
      },
      answers: ["any", "any", "any", "any", "any"],
      batch_number: 1,
    }, "csrf")
    await adoptionReplies("set-1", ["candidate-1"], "", "csrf")
    await commitAdoption("set-1", "candidate-1", "阿洛", "csrf")

    expect(vi.mocked(requestJson).mock.calls.map(([path]) => path)).toEqual([
      "/api/v1/me/adoption",
      "/api/v1/me/adoption/candidate-sets",
      "/api/v1/me/adoption/candidate-sets/set-1/replies",
      "/api/v1/me/adoption",
    ])
  })
})
