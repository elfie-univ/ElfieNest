import { describe, expect, it } from "vitest"

import { ownerElfiePath } from "./client"

describe("ownerElfiePath", () => {
  it("includes each supported management filter when supplied", () => {
    expect(ownerElfiePath({
      ownerUserId: "14",
      speciesId: "fox spirit",
      foodKey: "daily",
      embodimentState: "offline"
    })).toBe("/api/owner/elfies?owner_user_id=14&species_id=fox+spirit&food_key=daily&embodiment_state=offline")
  })

  it("keeps the unfiltered endpoint stable", () => {
    expect(ownerElfiePath()).toBe("/api/owner/elfies")
  })
})
