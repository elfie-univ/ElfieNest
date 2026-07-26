import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("ManagePage", () => {
  it("does not keep the account default-login preference inside the monitor panel", () => {
    const source = readFileSync(resolve(import.meta.dirname, "ManagePage.tsx"), "utf8")

    expect(source).not.toContain('title="默认打开页面"')
    expect(source).not.toContain("saveLandingPage")
  })
})
