import { beforeEach, describe, expect, it } from "vitest"

import { INITIAL_ADOPTION_STATE } from "./adoption-model"
import { loadAdoptionDraft } from "./adoption-storage"

describe("adoption storage", () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it("does not restore an interrupted invitation as a permanent waiting screen", async () => {
    window.localStorage.setItem("elfienest.adoption-draft.owner.v2", JSON.stringify({
      accountId: "owner",
      savedAt: Date.now(),
      sessionExpiresAt: Date.now() + 60_000,
      state: {
        ...INITIAL_ADOPTION_STATE,
        screen: "inviting",
        dirty: true,
        candidateSetId: "set-1",
        adoptionSessionId: "session-1",
        candidates: [{ candidateId: "candidate-1" }],
        selectedCandidateIds: ["candidate-1"],
      },
    }))

    const result = await loadAdoptionDraft("owner")

    expect(result.state?.screen).toBe("shortlist")
    expect(result.state?.selectedCandidateIds).toEqual(["candidate-1"])
  })
})
