import { resolve } from "node:path"

import { defineConfig } from "vite"

const frontendRoot = resolve(import.meta.dirname)
const webBuildDirectory = resolve(frontendRoot, "../../../../build/web")

export default defineConfig({
  root: frontendRoot,
  build: {
    emptyOutDir: true,
    manifest: "manifest.json",
    outDir: webBuildDirectory,
    rollupOptions: {
      input: {
        chat: resolve(frontendRoot, "chat.html"),
        login: resolve(frontendRoot, "login.html"),
        manage: resolve(frontendRoot, "manage.html")
      }
    }
  }
})
