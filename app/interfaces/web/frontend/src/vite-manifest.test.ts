import { describe, expect, it } from "vitest"

import { exposeDynamicImportAssets } from "./vite-manifest"

describe("Vite manifest dynamic imports", () => {
  it("adds lazy entries to the transitive import allow-list", () => {
    const manifest = {
      "index.html": {
        assets: ["assets/logo.png"],
        dynamicImports: ["src/profile-chart-runtime.ts"],
        file: "assets/app.js",
      },
      "src/profile-chart-runtime.ts": {
        file: "assets/profile-chart-runtime.js",
        isDynamicEntry: true,
      },
    }

    expect(exposeDynamicImportAssets(manifest)).toEqual({
      ...manifest,
      "index.html": {
        ...manifest["index.html"],
        imports: ["src/profile-chart-runtime.ts"],
      },
    })
  })
})
