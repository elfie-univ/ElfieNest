import { describe, expect, it } from "vitest"

import { ElfieIdValueSchema } from "./elfie-id"

describe("ElfieIdValueSchema", () => {
  it("accepts stable product ids instead of only numeric demo ids", () => {
    expect(ElfieIdValueSchema.parse("12345678")).toBe("12345678")
    expect(ElfieIdValueSchema.parse("elfie_default")).toBe("elfie_default")
    expect(ElfieIdValueSchema.parse("resident-1")).toBe("resident-1")
  })

  it("rejects blank, path-like, and unbounded values", () => {
    expect(ElfieIdValueSchema.safeParse("").success).toBe(false)
    expect(ElfieIdValueSchema.safeParse("with space").success).toBe(false)
    expect(ElfieIdValueSchema.safeParse("../elfie").success).toBe(false)
    expect(ElfieIdValueSchema.safeParse("e".repeat(129)).success).toBe(false)
  })
})
