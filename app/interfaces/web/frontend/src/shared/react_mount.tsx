import { createRoot } from "react-dom/client"
import type { ReactNode } from "react"

import "./styles.css"

export function mountProductPage(content: ReactNode): void {
  const mountPoint = document.getElementById("app")
  if (mountPoint === null) {
    throw new Error("ERR_MISSING_APP_MOUNT")
  }
  createRoot(mountPoint).render(content)
}
