import { resolve } from "node:path"

import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

const frontendRoot = resolve(import.meta.dirname)
const webBuildDirectory = resolve(frontendRoot, "../../../../build/web")

export default defineConfig({
  root: frontendRoot,
  plugins: [react(), tailwindcss()],
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
