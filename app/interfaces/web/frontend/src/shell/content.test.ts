import { describe, expect, it } from "vitest"

import { shellPages } from "./content"

describe("shellPages", () => {
  it("keeps login, chat, and manage as separate source shells", () => {
    // Given: the Web build foundation page catalogue.
    const pageNames = Object.keys(shellPages).sort()

    // When: the source shells are enumerated.

    // Then: each required entry page has its own shell definition.
    expect(pageNames).toEqual(["chat", "login", "manage"])
  })
})
