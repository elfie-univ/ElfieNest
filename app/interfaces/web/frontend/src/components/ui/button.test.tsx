import { describe, expect, it } from "vitest"

import { buttonVariants } from "./button"

describe("buttonVariants", () => {
  it("keeps application buttons readable and consistently sized", () => {
    const primary = buttonVariants({ variant: "default" })
    const outline = buttonVariants({ variant: "outline" })

    expect(primary).toContain("h-10")
    expect(primary).toContain("hover:bg-[var(--accent-hover)]")
    expect(primary).toContain("hover:text-[var(--surface)]")
    expect(outline).toContain("border-[var(--border-strong)]")
    expect(outline).toContain("bg-[var(--surface-field)]")
    expect(outline).toContain("hover:bg-[var(--surface-hover)]")
    expect(outline).toContain("hover:text-[var(--text)]")
  })
})
