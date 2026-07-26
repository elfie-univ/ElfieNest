import { describe, expect, it } from "vitest"

import { isManagerTab, MANAGER_NAV_GROUPS, MANAGER_NAV_ITEMS } from "./managerNavigation"

describe("MANAGER_NAV_ITEMS", () => {
  it("uses the approved Lucide icon key for every management destination", () => {
    expect(MANAGER_NAV_ITEMS.map((item) => item.icon)).toEqual([
      "activity", "users", "cat", "house", "plug-zap", "utensils", "wrench", "settings"
    ])
  })

  it("exposes only the approved desktop manager destinations in their final order", () => {
    expect(MANAGER_NAV_ITEMS.map(({ id, label }) => ({ id, label }))).toEqual([
      { id: "monitor", label: "状态监控" },
      { id: "users", label: "用户管理" },
      { id: "elfies", label: "精灵管理" },
      { id: "nest", label: "精灵巢管理" },
      { id: "providers", label: "模型订阅" },
      { id: "foods", label: "粮食策略" },
      { id: "tools", label: "工具与权限" },
      { id: "system", label: "系统设置" },
    ])
  })

  it("groups destinations without keeping retired routes addressable", () => {
    expect(MANAGER_NAV_GROUPS.map((group) => ({
      label: group.label,
      ids: group.items.map((item) => item.id),
    }))).toEqual([
      { label: "运行维护", ids: ["monitor"] },
      { label: "业务管理", ids: ["users", "elfies", "nest"] },
      { label: "模型订阅", ids: ["providers", "foods"] },
      { label: "系统配置", ids: ["tools", "system"] },
    ])
    expect(isManagerTab("logs")).toBe(false)
    expect(isManagerTab("models")).toBe(false)
    expect(isManagerTab("godot")).toBe(false)
  })
})
