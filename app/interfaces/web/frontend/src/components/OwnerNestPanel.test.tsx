import { describe, expect, it } from "vitest"

describe("Nest panel food boundary", () => {
  it("keeps emergency fallback out of the Elfie editor", () => {
    const fields = ["main_food_id", "main_food_options"]
    expect(fields).not.toContain("fallback_food")
    expect(fields).not.toContain("allowed_foods")
  })
})
