import { describe, expect, it } from "vitest"

import {
  INITIAL_ADOPTION_STATE,
  adoptionReducer,
  intentComplete,
  selectedName,
} from "./adoption-model"

describe("adoption journey model", () => {
  it("keeps basic and appearance choices independent", () => {
    const species = adoptionReducer(INITIAL_ADOPTION_STATE, { type: "set-basic", field: "speciesId", value: "fox" })
    const appearance = adoptionReducer(species, { type: "set-appearance", field: "stature", value: "tall" })

    expect(appearance.draft.speciesId).toBe("fox")
    expect(appearance.draft.stature).toBe("tall")
  })

  it("invalidates a candidate set when the intent changes", () => {
    const withCandidates = adoptionReducer(INITIAL_ADOPTION_STATE, {
      type: "candidates-ready",
      setId: "set-1",
      batch: 1,
      candidates: [],
    })
    const changed = adoptionReducer(withCandidates, { type: "set-answer", index: 0, value: "quiet" })

    expect(changed.candidateSetId).toBeNull()
    expect(changed.candidates).toEqual([])
    expect(changed.candidateBatch).toBe(0)
  })

  it("records the candidate batch and replaces the previous selection", () => {
    const first = adoptionReducer(INITIAL_ADOPTION_STATE, {
      type: "candidates-ready",
      setId: "set-1",
      batch: 1,
      candidates: [],
    })
    const selected = adoptionReducer(first, { type: "toggle-candidate", candidateId: "candidate-1" })
    const second = adoptionReducer(selected, {
      type: "candidates-ready",
      setId: "set-2",
      batch: 2,
      candidates: [],
    })

    expect(second.candidateBatch).toBe(2)
    expect(second.candidateSetId).toBe("set-2")
    expect(second.selectedCandidateIds).toEqual([])
  })

  it("requires one species and all five answers before generation", () => {
    let state = adoptionReducer(INITIAL_ADOPTION_STATE, { type: "set-basic", field: "speciesId", value: "dog" })
    expect(intentComplete(state.draft)).toBe(false)
    for (let index = 0; index < 5; index += 1) {
      state = adoptionReducer(state, { type: "set-answer", index, value: "any" })
    }
    expect(intentComplete(state.draft)).toBe(true)
  })

  it("resolves the final Earth name from the selected mode", () => {
    const state = adoptionReducer({
      ...INITIAL_ADOPTION_STATE,
      replies: [{
        candidateId: "candidate-1",
        originalName: "Aro",
        suggestedName: "Roro",
        speciesId: "fox",
        lifeStage: "young_adult",
        gender: "male",
        imageUrl: "/adoption/fox.svg",
        appearanceTags: [],
        personalityTags: [],
        introduction: "",
        compatibility: "",
        status: "accepted",
        message: "",
      }],
      finalCandidateId: "candidate-1",
    }, { type: "name-mode", mode: "suggested" })

    expect(selectedName(state)).toBe("Roro")
  })
})
