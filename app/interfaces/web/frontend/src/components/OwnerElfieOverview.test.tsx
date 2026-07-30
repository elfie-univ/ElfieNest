import { describe, expect, it } from "vitest"

import type { OwnerElfie } from "../api/owner-elfies"

describe("Elfie Main food contract", () => {
  it("contains one selection and eligible options", () => {
    const policy: OwnerElfie["food_policy"] = {
      main_food_id: "food_common",
      effective_main_food_id: "food_common",
      main_food_options: [{ food_id: "food_common", display_name: "常用粮" }],
      main_food_unavailable: false,
    }
    expect(policy.main_food_options).toHaveLength(1)
    expect("fallback_food" in policy).toBe(false)
  })
})
