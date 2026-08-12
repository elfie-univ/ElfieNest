import { beforeEach, describe, expect, it, vi } from "vitest"

import { ownerRead, ownerWrite } from "../http"
import { changeFoodLifecycle, ownerFoods } from "./food-packages"

vi.mock("../http", () => ({ ownerRead: vi.fn(), ownerWrite: vi.fn() }))

const food = {
  key: "food_common",
  display_name: "Common",
  system_role: "common" as const,
  enabled: false,
  archived: false,
  visibility_mode: "global" as const,
  visible_user_ids: [],
  roles: { primary: null, reasoning: null, vision: null, tool: null, fallback: null },
  health: "disabled",
  locality: "unknown",
  latest_evidence_at: null,
}

describe("versioned administrator Food client", () => {
  beforeEach(() => vi.clearAllMocks())

  it("reads only the dedicated Food package resource", async () => {
    vi.mocked(ownerRead).mockResolvedValue({
      version: 1,
      global_default_food_id: "food_common",
      global_emergency_food_id: "food_emergency",
      packages: [food],
      eligible_models: [],
    })

    const catalog = await ownerFoods()

    expect(catalog.packages[0]?.key).toBe("food_common")
    expect(ownerRead).toHaveBeenCalledWith("/api/v1/admin/food-packages")
  })

  it("writes lifecycle actions only through the versioned resource", async () => {
    vi.mocked(ownerWrite).mockResolvedValue(food)

    await changeFoodLifecycle("food_common", "disable", "csrf")

    expect(ownerWrite).toHaveBeenCalledWith(
      "/api/v1/admin/food-packages/food_common/disable",
      "POST",
      "csrf",
    )
  })
})
