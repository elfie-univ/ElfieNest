import { resolve } from "node:path"

import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const frontendRoot = resolve(import.meta.dirname)
const webBuildDirectory = resolve(frontendRoot, "../../../../build/web")

export default defineConfig({
  root: frontendRoot,
  plugins: [react()],
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
