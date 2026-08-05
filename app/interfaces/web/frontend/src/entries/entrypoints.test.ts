import { readFile } from "node:fs/promises"
import { resolve } from "node:path"

import { describe, expect, it } from "vitest"

const frontendRoot = resolve(import.meta.dirname, "../..")

describe("product entry shells", () => {
  it("keeps every server-routed page behind the single React shell", async () => {
    const shell = await readFile(resolve(frontendRoot, "index.html"), "utf8")

    expect(shell).toContain('<main id="app"></main>')
    expect(shell).toContain('src="/src/main.tsx"')
    expect(shell).toContain('href="../../../../docs/public/assets/favicon.ico"')
  })
})
