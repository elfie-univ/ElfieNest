import { readFile } from "node:fs/promises"
import { resolve } from "node:path"

import { describe, expect, it } from "vitest"

const consumers = [
  "BedDistribution.tsx",
  "ElfieIdentityCard.tsx",
  "OwnerFoodPanel.tsx",
  "OwnerProviderPanel.tsx",
] as const

describe("central formatter consumers", () => {
  it("removes component-owned locale and Intl assumptions", async () => {
    // Given: the four Task 4 components with known locale assumptions.
    const sources = await Promise.all(
      consumers.map((fileName) =>
        readFile(resolve(import.meta.dirname, "../components", fileName), "utf8"),
      ),
    )

    // When: direct locale/Intl calls are scanned at their former call sites.
    const forbiddenHits = sources.flatMap((source, index) => {
      const fileName = consumers[index]
      if (fileName === undefined) return []
      return source.match(/\.toLocale(?:String|DateString|TimeString)|\.localeCompare|new Intl\./g)
        ?.map((match) => `${fileName}:${match}`) ?? []
    })

    // Then: locale-sensitive work belongs only to src/i18n/format.ts.
    expect(forbiddenHits).toEqual([])
    for (const source of sources) {
      expect(source).toContain("currentLocale")
    }
  })
})
