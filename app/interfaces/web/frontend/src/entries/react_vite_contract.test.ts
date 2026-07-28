import { readFile } from "node:fs/promises"
import { resolve } from "node:path"

import { describe, expect, it } from "vitest"

const frontendRoot = resolve(import.meta.dirname, "../..")

type PackageManifest = {
  readonly dependencies?: Record<string, string>
  readonly devDependencies?: Record<string, string>
}

describe("React Vite product build", () => {
  it("uses one ReactDOM root and the Vite React integration", async () => {
    const [packageSource, viteSource, entrySource] = await Promise.all([
      readFile(resolve(frontendRoot, "package.json"), "utf8"),
      readFile(resolve(frontendRoot, "vite.config.ts"), "utf8"),
      readFile(resolve(frontendRoot, "src", "main.tsx"), "utf8")
    ])

    // When: the production entrypoint contract is checked.
    const packageManifest: PackageManifest = JSON.parse(packageSource)

    expect(packageManifest.dependencies?.["react"]).toBeDefined()
    expect(packageManifest.dependencies?.["react-dom"]).toBeDefined()
    expect(packageManifest.devDependencies?.["@vitejs/plugin-react"]).toBeDefined()
    expect(viteSource).toContain('import react from "@vitejs/plugin-react"')
    expect(viteSource).toContain('import tailwindcss from "@tailwindcss/vite"')
    expect(viteSource).toContain("plugins: [react(), tailwindcss()]")
    expect(entrySource).toContain('from "react-dom/client"')
    expect(entrySource).toContain("createRoot")
    expect(entrySource).toContain("<App />")
  })
})
