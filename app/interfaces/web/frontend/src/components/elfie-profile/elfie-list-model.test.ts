import { describe, expect, it } from "vitest"

import { filterElfieList, type ElfieListItem } from "./elfie-list-model"

function item(
  elfieId: string,
  name: string,
  speciesId: string,
  adopterAccountId: string,
): ElfieListItem {
  return {
    adopterAccountId,
    profile: {
      elfie_id: elfieId,
      name,
      species_id: speciesId,
      portrait_url: "",
    },
  }
}

const ITEMS = [
  item("23456789", "Kettle", "fox", "user123"),
  item("12345678", "Happy", "sun fox", "admin123"),
] as const

describe("Elfie list model", () => {
  it("searches name, species, and ID without case sensitivity", () => {
    expect(filterElfieList(ITEMS, "admin123", "HAPPY", "all").groups[0]?.items).toHaveLength(1)
    expect(filterElfieList(ITEMS, "admin123", "FOX", "all").visibleCount).toBe(2)
    expect(filterElfieList(ITEMS, "admin123", "23456789", "all").groups[0]?.items[0]?.profile.name).toBe("Kettle")
  })

  it("counts ownership from account IDs and orders mine before other", () => {
    const result = filterElfieList(ITEMS, "admin123", "", "all")

    expect(result.counts).toEqual({ all: 2, mine: 1, other: 1 })
    expect(result.groups.map((group) => group.kind)).toEqual(["mine", "other"])
    expect(result.groups[0]?.items[0]?.profile.name).toBe("Happy")
    expect(result.groups[1]?.items[0]?.profile.name).toBe("Kettle")
  })

  it("applies ownership filters after search without changing the total filter counts", () => {
    const mine = filterElfieList(ITEMS, "admin123", "fox", "mine")
    const other = filterElfieList(ITEMS, "admin123", "fox", "other")

    expect(mine.counts).toEqual({ all: 2, mine: 1, other: 1 })
    expect(mine.groups.flatMap((group) => group.items).map((entry) => entry.profile.name)).toEqual(["Happy"])
    expect(other.groups.flatMap((group) => group.items).map((entry) => entry.profile.name)).toEqual(["Kettle"])
  })
})
