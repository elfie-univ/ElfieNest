import { createRoot } from "react-dom/client"
import type { ReactNode } from "react"

import "./styles.css"

export function mountProductPage(content: ReactNode): void {
  const mountPoint = document.getElementById("app")
  if (mountPoint === null) {
    throw new Error("页面缺少 #app 挂载点")
  }
  createRoot(mountPoint).render(content)
}
