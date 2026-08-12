import { beforeEach, describe, expect, it, vi } from "vitest"

import { requestJson } from "../http"
import { adoptionCandidates, adoptionInfo, adoptionReplies, commitAdoption } from "./adoption"

vi.mock("../http", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../http")>()
  return { ...original, requestJson: vi.fn() }
})

const candidate = {
  candidate_id: "candidate-1",
  original_name: "阿洛",
  suggested_name: "洛洛",
  species_id: "fox" as const,
  life_stage: "young_adult" as const,
  gender: "male" as const,
  image_url: "/adoption/fox.svg",
  appearance_tags: ["高挑"],
  personality_tags: ["好奇探索"],
  introduction: "hello",
  compatibility: "steady",
}

describe("versioned current-member Adoption client", () => {
  beforeEach(() => vi.clearAllMocks())

  it("uses only the current-member Adoption resource", async () => {
    vi.mocked(requestJson)
      .mockResolvedValueOnce({
        personality_styles: ["好奇探索"],
        species_ids: ["fox"],
        heights: ["standard"],
        builds: ["standard"],
        life_stages: ["any"],
        quota: { used: 0, max: 3, remaining: 3, can_adopt: true },
      })
      .mockResolvedValueOnce({ candidate_set_id: "set-1", candidates: Array(5).fill(candidate) })
      .mockResolvedValueOnce({
        candidate_set_id: "set-1",
        replies: [{ ...candidate, status: "accepted", message: "yes" }],
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
    }, "csrf")
    await adoptionReplies("set-1", ["candidate-1"], "csrf")
    await commitAdoption("set-1", "candidate-1", "阿洛", "csrf")

    expect(vi.mocked(requestJson).mock.calls.map(([path]) => path)).toEqual([
      "/api/v1/me/adoption",
      "/api/v1/me/adoption/candidate-sets",
      "/api/v1/me/adoption/candidate-sets/set-1/replies",
      "/api/v1/me/adoption",
    ])
  })
})
