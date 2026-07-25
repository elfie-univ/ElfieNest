import { readFile } from "node:fs/promises"
import { resolve } from "node:path"

import { describe, expect, it } from "vitest"

const frontendRoot = resolve(import.meta.dirname, "../..")

type PackageManifest = {
  readonly dependencies?: Record<string, string>
  readonly devDependencies?: Record<string, string>
}

describe("React Vite product build", () => {
  it("uses ReactDOM roots and the Vite React integration for all page entries", async () => {
    // Given: the product frontend source and its build manifest.
    const [packageSource, viteSource, mountSource, entries] = await Promise.all([
      readFile(resolve(frontendRoot, "package.json"), "utf8"),
      readFile(resolve(frontendRoot, "vite.config.ts"), "utf8"),
      readFile(resolve(frontendRoot, "src", "shared", "react_mount.tsx"), "utf8"),
      Promise.all(
        ["login", "chat", "manage"].map((page) =>
          readFile(resolve(frontendRoot, "src", page, "main.tsx"), "utf8")
        )
      )
    ])

    // When: the production entrypoint contract is checked.
    const packageManifest: PackageManifest = JSON.parse(packageSource)

    // Then: Vite resolves JSX and each shell mounts through ReactDOM.
    expect(packageManifest.dependencies?.["react"]).toBeDefined()
    expect(packageManifest.dependencies?.["react-dom"]).toBeDefined()
    expect(packageManifest.devDependencies?.["@vitejs/plugin-react"]).toBeDefined()
    expect(viteSource).toContain('import react from "@vitejs/plugin-react"')
    expect(viteSource).toContain("plugins: [react()]")
    expect(mountSource).toContain('from "react-dom/client"')
    expect(mountSource).toContain("createRoot")
    for (const entry of entries) expect(entry).toContain("mountProductPage")
  })
})
