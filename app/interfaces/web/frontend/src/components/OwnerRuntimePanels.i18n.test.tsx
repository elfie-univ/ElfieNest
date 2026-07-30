import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError, ownerRead, ownerWrite } from "../api/client"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
import { ManageMonitorPanel } from "./ManageMonitorPanel"
import { OwnerDataPanel } from "./OwnerDataPanel"
import { OwnerModelPanel, OwnerToolPanel } from "./OwnerRuntimeCatalogPanels"

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return { ...original, ownerRead: vi.fn(), ownerWrite: vi.fn() }
})

describe("Task 14 runtime and raw-data panels", () => {
  beforeEach(() => {
    vi.mocked(ownerRead).mockImplementation(async (path) => {
      if (path === "/api/owner/models/") return [{
        model_id: "provider/qwen3:4b",
        provider: "provider",
        display_name: "Qwen 3 4B",
        capabilities: ["text", "tools"],
        context_window: 8192,
        cost_tier: 2,
        visible: true,
        active: true,
      }]
      if (path === "/api/owner/runtime/tools/") return { tools: { web_search: { endpoint: "https://tools.example/v1", enabled: true } } }
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

  it("renders English model, tool, and monitor labels while preserving technical values", async () => {
    // Given: English runtime panels backed by technical catalog values.
    const instance = createI18n()
    await instance.changeLanguage("en-US")
    document.documentElement.lang = "en-US"
    render(<I18nextProvider i18n={instance}><OwnerModelPanel csrfToken="csrf" /><OwnerToolPanel csrfToken="csrf" /><ManageMonitorPanel elfieCount={2} /></I18nextProvider>)

    // When: all runtime data loads.
    expect(await screen.findByRole("heading", { name: "Models" })).toBeInTheDocument()

    // Then: labels are English, unknown state is localized, and IDs remain exact.
    expect(screen.getByRole("heading", { name: "Tools" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Unified monitor" })).toBeInTheDocument()
    expect(screen.getByText("provider/qwen3:4b")).toBeInTheDocument()
    expect(screen.getByText("Needs attention")).toBeInTheDocument()
    expect(screen.queryByText("综合监控")).not.toBeInTheDocument()
  })

  it("preserves tool selection and raw JSON draft across locale switching", async () => {
    // Given: an English tool editor with a selected technical tool.
    const user = userEvent.setup()
    const instance = renderWithLocale(<OwnerToolPanel csrfToken="csrf" />, "en-US")
    await user.click(await screen.findByRole("button", { name: /web_search/ }))
    const editor = screen.getByRole("textbox", { name: "Tool JSON configuration" })
    fireEvent.change(editor, { target: { value: '{"endpoint":"https://changed.example/v1"}' } })

    // When: the shared locale switches to Chinese.
    await instance.changeLanguage("zh-CN")

    // Then: selection and exact draft bytes remain unchanged.
    expect(screen.getByRole("textbox", { name: "工具 JSON 配置" })).toHaveValue('{"endpoint":"https://changed.example/v1"}')
    expect(screen.getByRole("button", { name: /web_search/ })).toHaveClass("list-row--active")
  })

  it("localizes invalid raw JSON and hides backend details in English", async () => {
    // Given: an editable raw-data panel in English.
    const user = userEvent.setup()
    renderWithLocale(<OwnerDataPanel csrfToken="csrf" description="Technical config" readPath="/raw" title="Runtime config" writePath="/raw" />, "en-US")
    const editor = await screen.findByRole("textbox", { name: "Runtime config JSON configuration" })

    // When: invalid JSON is submitted.
    fireEvent.change(editor, { target: { value: "{" } })
    await user.click(screen.getByRole("button", { name: "Save configuration" }))

    // Then: a local English validation message is shown.
    expect(screen.getByRole("alert")).toHaveTextContent("Enter valid JSON.")

    // Given: the backend later rejects with Chinese natural-language detail.
    vi.mocked(ownerWrite).mockRejectedValueOnce(new ApiError(400, "后端拒绝了配置"))
    fireEvent.change(editor, { target: { value: '{"protocol_field":"raw_value"}' } })

    // When: the valid raw payload is submitted.
    await user.click(screen.getByRole("button", { name: "Save configuration" }))

    // Then: English uses a closed fallback and never leaks the backend detail.
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
