import { describe, expect, it } from "vitest"

import { MobileAccessSchema, OwnerSchema, ThemeKeySchema, ownerElfiePath } from "./client"

describe("ownerElfiePath", () => {
  it("includes each supported management filter when supplied", () => {
    expect(ownerElfiePath({
      ownerUserId: 42,
      speciesId: "fox spirit",
      foodKey: "daily",
      embodimentState: "offline"
    })).toBe("/api/owner/elfies?owner_user_id=42&species_id=fox+spirit&food_key=daily&embodiment_state=offline")
  })

  it("keeps the unfiltered endpoint stable", () => {
    expect(ownerElfiePath()).toBe("/api/owner/elfies")
  })

  it("rejects legacy owner usernames and string user ids at the API boundary", () => {
    expect(OwnerSchema.safeParse({ user_id: "42", account_id: "member42", display_name: null }).success).toBe(false)
    expect(OwnerSchema.safeParse({ user_id: 42, account_id: "member42", display_name: "Member", username: "legacy" }).success).toBe(false)
  })

  it("accepts only a typed LAN mobile-access response", () => {
    expect(MobileAccessSchema.parse({
      available: true,
      urls: ["http://192.168.1.8:8000/"]
    })).toEqual({
      available: true,
      urls: ["http://192.168.1.8:8000/"]
    })
  })

  it("keeps the four supported visual themes explicit", () => {
    expect(ThemeKeySchema.parse("warm-paper")).toBe("warm-paper")
    expect(ThemeKeySchema.parse("harbor-blue")).toBe("harbor-blue")
    expect(ThemeKeySchema.parse("orchid-archive")).toBe("orchid-archive")
    expect(ThemeKeySchema.parse("moss-green")).toBe("moss-green")
    expect(ThemeKeySchema.safeParse("graphite").success).toBe(false)
  })

})
