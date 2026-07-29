import { describe, expect, it } from "vitest"

import { ChatMessageSchema, MobileAccessSchema, ThemeKeySchema, ownerElfiePath } from "./client"

describe("ownerElfiePath", () => {
  it("includes each supported management filter when supplied", () => {
    expect(ownerElfiePath({
      ownerAccountId: "alice",
      speciesId: "fox spirit",
      foodKey: "daily",
      embodimentState: "offline"
    })).toBe("/api/owner/elfies?owner_account_id=alice&species_id=fox+spirit&food_key=daily&embodiment_state=offline")
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

  it("accepts stable non-numeric Elfie ids from the product API", () => {
    expect(ChatMessageSchema.parse({
      id: 1,
      elfie_id: "elfie_default",
      sender: "elfie",
      text: "你好",
      created_at: "2026-07-28T00:00:00Z",
    }).elfie_id).toBe("elfie_default")
  })
})
