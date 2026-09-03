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
      sessionId: "session-1",
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
      sessionId: "session-1",
      batch: 1,
      candidates: [],
    })
    const selected = adoptionReducer(first, { type: "toggle-candidate", candidateId: "candidate-1" })
    const second = adoptionReducer(selected, {
      type: "candidates-ready",
      setId: "set-2",
      sessionId: "session-1",
      batch: 2,
      candidates: [],
    })

    expect(second.candidateBatch).toBe(2)
    expect(second.candidateSetId).toBe("set-2")
    expect(second.selectedCandidateIds).toEqual([])
  })

  it("uses the five quick answers by default and still validates missing answers", () => {
    let state = adoptionReducer(INITIAL_ADOPTION_STATE, { type: "set-basic", field: "speciesId", value: "dog" })
    expect(intentComplete(state.draft)).toBe(true)

    const incomplete = {
      ...state.draft,
      answers: state.draft.answers.map((answer, index) => index === 2 ? null : answer),
    }
    expect(intentComplete(incomplete)).toBe(false)
  })

  it("keeps only one candidate selected", () => {
    const first = adoptionReducer(INITIAL_ADOPTION_STATE, { type: "toggle-candidate", candidateId: "candidate-1" })
    const second = adoptionReducer(first, { type: "toggle-candidate", candidateId: "candidate-2" })
    const cleared = adoptionReducer(second, { type: "toggle-candidate", candidateId: "candidate-2" })

    expect(first.selectedCandidateIds).toEqual(["candidate-1"])
    expect(second.selectedCandidateIds).toEqual(["candidate-2"])
    expect(cleared.selectedCandidateIds).toEqual([])
  })

  it("resumes legacy review and reply drafts on a visible current screen", () => {
    const review = adoptionReducer(INITIAL_ADOPTION_STATE, {
      type: "restore",
      state: { ...INITIAL_ADOPTION_STATE, screen: "review", dirty: true },
    })
    const replies = adoptionReducer(INITIAL_ADOPTION_STATE, {
      type: "restore",
      state: { ...INITIAL_ADOPTION_STATE, screen: "replies", finalCandidateId: "candidate-1", dirty: true },
    })

    expect(review.screen).toBe("basic")
    expect(replies.screen).toBe("naming")
  })

  it("resolves the final Earth name from the selected mode", () => {
    const state = adoptionReducer({
      ...INITIAL_ADOPTION_STATE,
      replies: [{
        candidateId: "candidate-1",
        speciesId: "fox",
        lifeStage: "young_adult",
        ageYears: 3,
        gender: "male",
        fullBodyImageUrl: "",
        headshotImageUrl: "",
        runtimeAppearance: {},
        appearanceTags: [],
        personalityTags: [],
        status: "accepted",
        message: "",
      }],
      finalCandidateId: "candidate-1",
    }, { type: "custom-name", value: "Roro" })

    expect(selectedName(state)).toBe("Roro")
  })
})
