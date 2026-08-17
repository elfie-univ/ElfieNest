import { describe, expect, it } from "vitest"

import { MobileAccessSchema, ThemeKeySchema } from "./client"

describe("client schemas", () => {
  it("accepts only a typed LAN mobile-access response", () => {
    expect(MobileAccessSchema.parse({
      available: true,
      network_name: "Elfie Home",
      urls: ["http://192.168.1.8:15212/"]
    })).toEqual({
      available: true,
      network_name: "Elfie Home",
      urls: ["http://192.168.1.8:15212/"]
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
