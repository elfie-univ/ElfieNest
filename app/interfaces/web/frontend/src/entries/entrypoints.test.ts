import { readFile } from "node:fs/promises"
import { resolve } from "node:path"

import { describe, expect, it } from "vitest"

const frontendRoot = resolve(import.meta.dirname, "../..")

describe("product entry shells", () => {
  it("keeps each server-routed page as a generated Vite shell", async () => {
    // Given: the three HTML files served by the Core page routes.
    const shells = await Promise.all(
      ["login", "chat", "manage"].map(async (page) => ({
        page,
        html: await readFile(resolve(frontendRoot, `${page}.html`), "utf8")
      }))
    )

    // When: their source entry modules are inspected after the React migration.

    // Then: every route retains its own #app mount point and Vite module entry.
    for (const shell of shells) {
      expect(shell.html).toContain('<main id="app"></main>')
      expect(shell.html).toContain(`src="/src/${shell.page}/main.tsx"`)
    }
  })
})
