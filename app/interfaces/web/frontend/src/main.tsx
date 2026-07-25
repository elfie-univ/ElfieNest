import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { App } from "./App"
import "./styles.css"
import { SessionProvider } from "./stores/session"

const mount = document.querySelector<HTMLElement>("#app")
if (mount === null) throw new Error("页面缺少 #app 挂载点")

createRoot(mount).render(<StrictMode><SessionProvider><App /></SessionProvider></StrictMode>)
