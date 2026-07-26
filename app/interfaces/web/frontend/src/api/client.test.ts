import { describe, expect, it } from "vitest"

import { MobileAccessSchema, ThemeKeySchema, ownerElfiePath } from "./client"

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
