import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ownerRead, ownerWrite } from "../api/client"
import { ApiError } from "../api/http"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
import { SystemSettingsPanel } from "./SystemSettingsPanel"
import { ToastProvider } from "./ui/toast"

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return { ...original, ownerRead: vi.fn(), ownerWrite: vi.fn() }
})

const engine = { tick_interval_sec: 1.5, max_elfies_per_room: null }
const adoption = { max_elfies_per_user: 3, allowed_species_ids: ["dog", "fox"], personality_presets_enabled: {} }
const security = { session_ttl_days: 7, rate_limit: { max_attempts: 5, window_seconds: 60 } }

describe("SystemSettingsPanel", () => {
  beforeEach(() => {
    vi.mocked(ownerRead).mockImplementation(async (path) => {
      if (path.endsWith("/engine")) return engine
      if (path.endsWith("/adoption")) return adoption
      return security
    })
    vi.mocked(ownerWrite).mockResolvedValue({})
  })

  it("uses shared bounded controls and saves only the selected module", async () => {
    const user = userEvent.setup()
    renderSettingsPanel()

    await user.click(await screen.findByRole("button", { name: "增加运行 Tick（秒）" }))
    await user.click(screen.getByRole("button", { name: "保存引擎设置" }))

    await waitFor(() => expect(vi.mocked(ownerWrite)).toHaveBeenCalledWith(
      "/api/owner/system/engine",
      "PUT",
      "csrf",
      { tick_interval_sec: 1.6, max_elfies_per_room: null },
    ))
    expect(screen.getByRole("checkbox", { name: "狗" })).toBeChecked()
    expect(screen.getByRole("checkbox", { name: "狐狸" })).toBeChecked()
  })

  it("renders English settings and hides backend save detail", async () => {
    // Given: English system settings and a backend save failure with Chinese detail.
    const user = userEvent.setup()
    vi.mocked(ownerWrite).mockRejectedValueOnce(new ApiError(400, "后端拒绝了系统设置"))
    renderSettingsPanel("en-US")

    // When: only the engine module is changed and saved.
    expect(await screen.findByRole("heading", { name: "Engine settings" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Save engine settings" }))

    // Then: the English fallback is shown and backend detail remains hidden.
    expect(screen.queryByText("Control the local Nest rhythm and room capacity.")).not.toBeInTheDocument()
    expect(screen.queryByText("0.1-3600 seconds")).not.toBeInTheDocument()
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to save management data.")
    expect(screen.queryByText("后端拒绝了系统设置")).not.toBeInTheDocument()
  })
})

function renderSettingsPanel(locale: SupportedLocale = "zh-CN"): void {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  document.documentElement.lang = locale
  render(
    <I18nextProvider i18n={instance}>
      <ToastProvider><SystemSettingsPanel csrfToken="csrf" /></ToastProvider>
    </I18nextProvider>,
  )
}
