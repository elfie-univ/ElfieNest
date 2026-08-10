import { beforeEach, describe, expect, it, vi } from "vitest"

import { ownerWrite, requestJson } from "../http"
import { elfieFoodPolicy, updateElfieFoodPolicy } from "./food-policy"

vi.mock("../http", () => ({ ownerWrite: vi.fn(), requestJson: vi.fn() }))

const policy = {
  main_food_id: "food_common",
  effective_main_food_id: "food_common",
  main_food_options: [{ food_id: "food_common", display_name: "Common" }],
  main_food_unavailable: false,
}

describe("versioned Elfie Food policy client", () => {
  beforeEach(() => vi.clearAllMocks())

  it("reads and writes the Elfie-owned Food policy resource", async () => {
    vi.mocked(requestJson).mockResolvedValue(policy)
    vi.mocked(ownerWrite).mockResolvedValue(policy)

    await elfieFoodPolicy("00000001")
    await updateElfieFoodPolicy("00000001", "food_common", "csrf")

    expect(requestJson).toHaveBeenCalledWith(
      "/api/v1/elfies/00000001/food-policy",
    )
    expect(ownerWrite).toHaveBeenCalledWith(
      "/api/v1/elfies/00000001/food-policy",
      "PUT",
      "csrf",
      { main_food_id: "food_common" },
    )
  })

  it("rejects undeclared response fields", async () => {
    vi.mocked(requestJson).mockResolvedValue({ ...policy, legacy: true })
    await expect(elfieFoodPolicy("00000001")).rejects.toThrow()
  })
})
