import { beforeEach, describe, expect, it, vi } from "vitest"

import { requestJson } from "../http"
import { adminElfies, adminElfiesPath } from "./elfies"

vi.mock("../http", () => ({ requestJson: vi.fn() }))

const profile = {
  elfie_id: "00000001", name: "Mochi", species_id: "fox", gender: null,
  birth_date: null, summary: null, adopted_at: "2026-08-01",
  profile_status: "empty", big_five: null, personality_tags: [],
  portrait_url: "", appearance: null,
}

describe("administrator Elfies client", () => {
  beforeEach(() => vi.clearAllMocks())

  it("uses the strict versioned identity resource", async () => {
    vi.mocked(requestJson).mockResolvedValue({ items: [{
      owner: { user_id: 1, account_id: "owner", display_name: "Owner" },
      permissions: { can_view_profile: true, can_view_cognition: false },
      profile,
    }] })

    expect(await adminElfies({ ownerUserId: 1, speciesId: "fox" })).toHaveLength(1)
    expect(requestJson).toHaveBeenCalledWith(
      "/api/v1/admin/elfies?owner_user_id=1&species_id=fox",
    )
    expect(adminElfiesPath()).toBe("/api/v1/admin/elfies")
  })
})
