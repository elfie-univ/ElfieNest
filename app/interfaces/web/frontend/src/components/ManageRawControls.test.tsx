import { describe, expect, it } from "vitest"

import { FoodCatalogSchema } from "../api/owner-foods"

describe("food contract", () => {
  it("accepts only stable packages and model-role references", () => {
    const catalog = FoodCatalogSchema.parse({
      version: 1,
      global_default_food_id: "food_common",
      global_emergency_food_id: "food_emergency",
      eligible_models: [],
      packages: [{
        key: "food_emergency",
        display_name: "保底粮",
        system_role: "emergency",
        enabled: false,
        archived: false,
        roles: { primary: null, reasoning: null, vision: null, tool: null, fallback: [] },
        health: "disabled",
        locality: "unknown",
        latest_evidence_at: null,
      }],
    })
    expect(catalog.packages[0]?.roles.primary).toBeNull()
    expect(JSON.stringify(catalog)).not.toContain("max_tokens")
  })
})
