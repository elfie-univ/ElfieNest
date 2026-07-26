import { describe, expect, it } from "vitest"

import { MANAGER_NAV_ITEMS } from "./managerNavigation"

describe("MANAGER_NAV_ITEMS", () => {
  it("uses the approved Lucide icon key for every management destination", () => {
    expect(MANAGER_NAV_ITEMS.map((item) => item.icon)).toEqual([
      "activity", "scroll", "cat", "house", "users", "plug-zap", "menu", "utensils", "wrench", "settings", "cuboid"
    ])
  })
})
