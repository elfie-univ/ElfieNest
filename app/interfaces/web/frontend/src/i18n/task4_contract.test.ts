import { access } from "node:fs/promises"
import { resolve } from "node:path"

import { describe, expect, it } from "vitest"

describe("Task 4 locale service contract", () => {
  it("provides central formatting and localized-error modules before consumers migrate", async () => {
    // Given: the two central modules required by the Task 4 boundary.
    const expectedPaths = ["format.ts", "errors.ts"] as const

    // When: their source paths are inspected without importing an absent module.
    const existingPaths = await Promise.all(
      expectedPaths.map(async (relativePath) => {
        try {
          await access(resolve(import.meta.dirname, relativePath))
          return relativePath
        } catch (error) {
          if (error instanceof Error) return null
          throw error
        }
      }),
    )

    // Then: both central contracts must exist before page-level call sites use them.
    expect(existingPaths.filter((relativePath) => relativePath !== null)).toEqual(
      expectedPaths,
    )
  })
})
