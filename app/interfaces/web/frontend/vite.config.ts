import { resolve } from "node:path"
import { readFile, writeFile } from "node:fs/promises"

import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import type { Plugin } from "vite"
import { defineConfig } from "vitest/config"

import { exposeDynamicImportAssets } from "./src/vite-manifest"

const frontendRoot = resolve(import.meta.dirname)
const webBuildDirectory = resolve(frontendRoot, "../../../../build/web")

function exposeLazyAssetsToWebHost(): Plugin {
  return {
    name: "elfienest-web-manifest-lazy-assets",
    async closeBundle() {
      const manifestPath = resolve(webBuildDirectory, "manifest.json")
      const manifest: unknown = JSON.parse(await readFile(manifestPath, "utf8"))
      await writeFile(
        manifestPath,
        `${JSON.stringify(exposeDynamicImportAssets(manifest), null, 2)}\n`,
        "utf8",
      )
    },
  }
}

export default defineConfig({
  root: frontendRoot,
  plugins: [react(), tailwindcss(), exposeLazyAssetsToWebHost()],
  resolve: {
    alias: {
      "@": resolve(frontendRoot, "src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: [resolve(frontendRoot, "src/test/setup.ts")],
  },
  build: {
    emptyOutDir: true,
    manifest: "manifest.json",
    outDir: webBuildDirectory,
    rollupOptions: {
      input: {
        app: resolve(frontendRoot, "index.html")
      }
    }
  }
})
