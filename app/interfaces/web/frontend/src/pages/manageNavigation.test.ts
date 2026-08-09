import { describe, expect, it } from "vitest"

import { isManageTab, MANAGE_NAV_GROUPS, MANAGE_NAV_ITEMS } from "./manageNavigation"

describe("MANAGE_NAV_ITEMS", () => {
  it("uses the approved Lucide icon key for every management destination", () => {
    expect(MANAGE_NAV_ITEMS.map((item) => item.icon)).toEqual([
      "activity", "users", "cat", "house", "plug-zap", "utensils", "settings"
    ])
  })

  it("exposes only the approved desktop manage destinations in their final order", () => {
    expect(MANAGE_NAV_ITEMS.map((item) => item.id)).toEqual([
      "monitor", "users", "elfies", "nest", "providers", "foods", "system",
    ])
    expect(MANAGE_NAV_ITEMS.every((item) => Object.keys(item).sort().join(",") === "icon,id")).toBe(true)
  })

  it("groups destinations without keeping retired routes addressable", () => {
    expect(MANAGE_NAV_GROUPS.map((group) => ({
      id: group.id,
      ids: group.items.map((item) => item.id),
    }))).toEqual([
      { id: "operations", ids: ["monitor"] },
      { id: "business", ids: ["users", "elfies", "nest"] },
      { id: "models", ids: ["providers", "foods"] },
      { id: "system", ids: ["system"] },
    ])
    expect(isManageTab("logs")).toBe(false)
    expect(isManageTab("models")).toBe(false)
    expect(isManageTab("godot")).toBe(false)
  })
})
