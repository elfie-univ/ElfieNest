import { readdirSync, readFileSync } from "node:fs"
import { dirname, extname, join, relative } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const SRC_ROOT = dirname(dirname(fileURLToPath(import.meta.url)))
const PRODUCT_API = /["'`](\/api\/[^"'`\s]*)/g
const DIRECT_TRANSPORT = /\b(?:fetch|requestJson|ownerRead|ownerWrite)\s*\(/

function productionSources(root: string): readonly string[] {
  const files: string[] = []
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const path = join(root, entry.name)
    if (entry.isDirectory()) files.push(...productionSources(path))
    if (
      entry.isFile()
      && [".ts", ".tsx"].includes(extname(entry.name))
      && !entry.name.includes(".test.")
    ) files.push(path)
  }
  return files
}

describe("frontend App API boundary", () => {
  it("keeps product API paths versioned outside the sole health exception", () => {
    const offenders: string[] = []
    for (const path of productionSources(SRC_ROOT)) {
      const source = readFileSync(path, "utf8")
      for (const match of source.matchAll(PRODUCT_API)) {
        const apiPath = match[1] ?? ""
        if (!apiPath.startsWith("/api/v1/") && apiPath !== "/api/health") {
          offenders.push(`${relative(SRC_ROOT, path)}: ${apiPath}`)
        }
      }
    }
    expect(offenders).toEqual([])
  })

  it("keeps paths and transport calls out of pages, components, and stores", () => {
    const offenders: string[] = []
    for (const area of ["pages", "components", "stores"]) {
      for (const path of productionSources(join(SRC_ROOT, area))) {
        const source = readFileSync(path, "utf8")
        if (PRODUCT_API.test(source) || DIRECT_TRANSPORT.test(source)) {
          offenders.push(relative(SRC_ROOT, path))
        }
        PRODUCT_API.lastIndex = 0
      }
    }
    expect(offenders).toEqual([])
  })
})
