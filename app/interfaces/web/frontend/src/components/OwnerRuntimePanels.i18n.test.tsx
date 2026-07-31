import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError, ownerRead, ownerWrite } from "../api/client"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
import { ManageMonitorPanel } from "./ManageMonitorPanel"
import { OwnerDataPanel } from "./OwnerDataPanel"

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return { ...original, ownerRead: vi.fn(), ownerWrite: vi.fn() }
})

describe("runtime and raw-data panel behavior", () => {
  beforeEach(() => {
    vi.mocked(ownerRead).mockImplementation(async (path) => {
      if (path === "/api/owner/runtime/status") return {
        status: "mystery",
        providers: { total: 1, active: 0, inactive: 1 },
        models: { total: 1, visible: 1, hidden: 0 },
        fallback: { provider: "provider/qwen3:4b", configured: true },
        observer: { event_count: 0, last_event: null },
        notes: [],
      }
      return { endpoint: "https://raw.example/v1", protocol_field: "raw_value" }
    })
    vi.mocked(ownerWrite).mockResolvedValue({ saved: true })
  })

  it("renders the monitor in English while preserving technical values", async () => {
    renderWithLocale(<ManageMonitorPanel elfieCount={2} />, "en-US")

    expect(await screen.findByRole("heading", { name: "Unified monitor" })).toBeInTheDocument()
    expect(screen.getByText(/provider\/qwen3:4b/)).toBeInTheDocument()
    expect(screen.getByText("Needs attention")).toBeInTheDocument()
    expect(screen.queryByText("综合监控")).not.toBeInTheDocument()
  })

  it("preserves a raw JSON draft across locale switching", async () => {
    const instance = renderWithLocale(
      <OwnerDataPanel csrfToken="csrf" description="Technical config" readPath="/raw" title="Runtime config" writePath="/raw" />,
      "en-US",
    )
    const editor = await screen.findByRole("textbox", { name: "Runtime config JSON configuration" })
    fireEvent.change(editor, { target: { value: "{\"endpoint\":\"https://changed.example/v1\"}" } })

    await instance.changeLanguage("zh-CN")

    expect(screen.getByRole("textbox", { name: "Runtime config JSON 配置" })).toHaveValue("{\"endpoint\":\"https://changed.example/v1\"}")
  })

  it("localizes invalid JSON and hides backend details in English", async () => {
    const user = userEvent.setup()
    renderWithLocale(
      <OwnerDataPanel csrfToken="csrf" description="Technical config" readPath="/raw" title="Runtime config" writePath="/raw" />,
      "en-US",
    )
    const editor = await screen.findByRole("textbox", { name: "Runtime config JSON configuration" })

    fireEvent.change(editor, { target: { value: "{" } })
    await user.click(screen.getByRole("button", { name: "Save configuration" }))
    expect(screen.getByRole("alert")).toHaveTextContent("Enter valid JSON.")

    vi.mocked(ownerWrite).mockRejectedValueOnce(new ApiError(400, "后端拒绝了配置"))
    fireEvent.change(editor, { target: { value: "{\"protocol_field\":\"raw_value\"}" } })
    await user.click(screen.getByRole("button", { name: "Save configuration" }))

    expect(screen.getByRole("alert")).toHaveTextContent("Unable to save management data.")
    expect(screen.queryByText("后端拒绝了配置")).not.toBeInTheDocument()
    expect(ownerWrite).toHaveBeenCalledWith("/raw", "PUT", "csrf", { protocol_field: "raw_value" })
  })
})

function renderWithLocale(node: React.ReactNode, locale: SupportedLocale): ReturnType<typeof createI18n> {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  document.documentElement.lang = locale
  render(<I18nextProvider i18n={instance}>{node}</I18nextProvider>)
  return instance
}
