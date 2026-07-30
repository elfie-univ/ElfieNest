import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { I18nextProvider } from "react-i18next"

import { App } from "./App"
import { createI18n } from "./i18n/config"
import { getBrowserStorage, initializeLocale } from "./i18n/locale"
import "./styles.css"
import { SessionProvider } from "./stores/session"

const i18nInstance = createI18n()
initializeLocale(i18nInstance, {
  storage: getBrowserStorage(window),
  browserLanguages:
    navigator.languages.length > 0 ? navigator.languages : [navigator.language],
  documentElement: document.documentElement,
})

if (import.meta.env.DEV) {
  void Promise.all([
    import("react-grab"),
    import("react-scan").then((reactScan) => {
      reactScan.scan({ enabled: true })
    }),
  ])
}

const mount = document.querySelector<HTMLElement>("#app")
if (mount === null) throw new Error("ERR_MISSING_APP_MOUNT")

createRoot(mount).render(
  <StrictMode>
    <I18nextProvider i18n={i18nInstance}>
      <SessionProvider>
        <App />
      </SessionProvider>
    </I18nextProvider>
  </StrictMode>,
)
