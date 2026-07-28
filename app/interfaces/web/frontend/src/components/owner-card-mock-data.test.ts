import { describe, expect, it } from "vitest"

import { MOCK_ELFIES, MOCK_USERS } from "./owner-card-mock-data"

describe("owner card mock data", () => {
  it("includes an Owner and a regular user", () => {
    expect(MOCK_USERS.map((user) => user.role)).toEqual(["owner", "user"])
  })

  it("uses readable eight-digit Elfie IDs", () => {
    expect(MOCK_ELFIES.map((elfie) => elfie.elfie_id)).toEqual(["12345678", "23456789"])
  })
})
