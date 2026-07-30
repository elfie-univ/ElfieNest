import { readFile } from "node:fs/promises"
import { resolve } from "node:path"

import { describe, expect, it } from "vitest"
import { z } from "zod"

const frontendRoot = resolve(import.meta.dirname, "../..")

const packageManifestSchema = z.object({
  scripts: z.record(z.string()).optional(),
  dependencies: z.record(z.string()).optional(),
  devDependencies: z.record(z.string()).optional(),
})

const developmentToolNames = ["react-grab", "react-scan", "react-doctor"] as const

function findDevelopmentToolMarkers(source: string): readonly string[] {
  return developmentToolNames.filter((toolName) => source.includes(toolName))
}

describe("React Vite product build", () => {
  it("uses one ReactDOM root and the Vite React integration", async () => {
    const [packageSource, viteSource, entrySource] = await Promise.all([
      readFile(resolve(frontendRoot, "package.json"), "utf8"),
      readFile(resolve(frontendRoot, "vite.config.ts"), "utf8"),
      readFile(resolve(frontendRoot, "src", "main.tsx"), "utf8")
    ])

    // When: the production entrypoint contract is checked.
    const packageManifest = packageManifestSchema.parse(JSON.parse(packageSource))

    expect(packageManifest.dependencies?.["react"]).toBeDefined()
    expect(packageManifest.dependencies?.["react-dom"]).toBeDefined()
    expect(packageManifest.devDependencies?.["@vitejs/plugin-react"]).toBeDefined()
    expect(viteSource).toContain('import react from "@vitejs/plugin-react"')
    expect(viteSource).toContain('import tailwindcss from "@tailwindcss/vite"')
    expect(viteSource).toContain(
      "plugins: [react(), tailwindcss(), exposeLazyAssetsToWebHost()]",
    )
    expect(entrySource).toContain('from "react-dom/client"')
    expect(entrySource).toContain("createRoot")
    expect(entrySource).toContain("<App />")
  })

  it("keeps React inspection tools behind the Vite development gate", async () => {
    // Given: the package manifest and production entrypoint are the only product gates.
    const [packageSource, entrySource] = await Promise.all([
      readFile(resolve(frontendRoot, "package.json"), "utf8"),
      readFile(resolve(frontendRoot, "src", "main.tsx"), "utf8"),
    ])

    // When: the development-tool contract is inspected.
    const packageManifest = packageManifestSchema.parse(JSON.parse(packageSource))
    const developmentGate = entrySource.match(
      /if\s*\(import\.meta\.env\.DEV\)\s*\{([\s\S]*?)\}/,
    )
    const developmentGateSource = developmentGate?.[1] ?? ""

    // Then: runtime overlays are development-only dynamic imports and Doctor is a CLI.
    for (const toolName of developmentToolNames) {
      expect(packageManifest.dependencies?.[toolName]).toBeUndefined()
      expect(packageManifest.devDependencies?.[toolName]).toBeDefined()
    }
    expect(packageManifest.scripts?.["doctor"]).toContain("react-doctor")
    expect(developmentGate).not.toBeNull()
    expect(findDevelopmentToolMarkers(developmentGateSource)).toEqual([
      "react-grab",
      "react-scan",
    ])
    expect(entrySource).not.toMatch(
      /^\s*import\s+.+["']react-(?:grab|scan)["']/m,
    )
  })

  it("detects a development tool marker in a controlled production fixture", () => {
    // Given: a production fixture accidentally contains one development overlay marker.
    const leakedProductionFixture = "assets/app.js: react-scan overlay"

    // When: production text is scanned with the same marker set as manual QA.
    const leaks = findDevelopmentToolMarkers(leakedProductionFixture)

    // Then: the leak is surfaced instead of producing a misleading empty result.
    expect(leaks).toEqual(["react-scan"])
  })
})
