import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import { saveProviderModels, updateProviderModel, type ProviderConnection } from "../api/owner-providers"
import { createI18n } from "../i18n/config"
import { ProviderModelsDialog } from "./ProviderModelsDialog"
import { ToastProvider } from "./ui/toast"

vi.mock("../api/owner-providers", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-providers")>()
  return {
    ...original,
    addProviderModel: vi.fn(),
    refreshProviderModels: vi.fn(),
    saveProviderModels: vi.fn(),
    updateProviderModel: vi.fn(),
  }
})

const connection = {
  connection_id: "conn-openai",
  catalog_id: "openai",
  alias: "OpenAI Main",
  api_base: "https://api.openai.com/v1",
  api_mode: "chat_completions",
  auth_type: "bearer",
  has_api_key: true,
  enabled: true,
  archived: false,
  usage_scope: "remote",
  verification: { status: "passed", checked_at: "2026-07-30T00:00:00Z", latency_ms: 42, error: null },
  models: [
    {
      id: "gpt-test",
      display_name: "GPT Test",
      canonical_model_id: "gpt-test",
      source: "official",
      context_window_tokens: 128000,
      max_output_tokens: 4096,
      supports_tools: true,
      supports_vision: false,
      supports_reasoning: null,
      hidden: false,
      retired: false,
      available: true,
      verification: { status: "passed", checked_at: "2026-07-30T00:00:00Z", latency_ms: 42, error: null },
    },
    {
      id: "manual-model",
      display_name: "Manual model",
      canonical_model_id: null,
      source: "manual",
      context_window_tokens: null,
      max_output_tokens: null,
      supports_tools: null,
      supports_vision: null,
      supports_reasoning: null,
      hidden: true,
      retired: false,
      available: false,
      verification: { status: "never", checked_at: null, latency_ms: null, error: null },
    },
  ],
  model_refresh: null,
} satisfies ProviderConnection

describe("ProviderModelsDialog", () => {
  beforeAll(() => {
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
  })

  beforeEach(() => {
    vi.mocked(saveProviderModels).mockResolvedValue(connection)
    vi.mocked(updateProviderModel).mockResolvedValue(connection.models[0]!)
  })

  it("keeps capability symbols compact in read and edit states", async () => {
    const user = userEvent.setup()
    renderDialog()

    const dialog = screen.getByRole("dialog", { name: "OpenAI Main 的模型" })
    expect(within(dialog).queryByText("模型 ID 会原样发送给当前订阅；显示名称用于跨订阅识别同一模型。")).not.toBeInTheDocument()
    const firstModelRow = within(dialog).getAllByRole("row")[1]!
    const capabilityCell = firstModelRow.querySelector(".provider-model-capabilities")
    expect(capabilityCell).not.toBeNull()
    if (!capabilityCell) return
    expect(capabilityCell).toHaveTextContent("❌/✅/?")
    expect(capabilityCell.querySelectorAll(".provider-model-capability-separator")).toHaveLength(2)
    expect(capabilityCell).not.toHaveTextContent("视觉")
    expect(capabilityCell).not.toHaveTextContent("工具")
    expect(capabilityCell).not.toHaveTextContent("推理")
    const status = firstModelRow.querySelector(".provider-model-status")
    expect(status).not.toBeNull()
    if (!status) return
    expect(status).toHaveTextContent("可用/42ms")
    expect(status.querySelector(".provider-model-status-separator")).not.toBeNull()

    await user.click(within(dialog).getByRole("button", { name: "编辑全部" }))
    expect(within(firstModelRow).getAllByRole("spinbutton")).toHaveLength(2)
    const capabilitySelects = within(firstModelRow).getAllByRole("combobox")
    expect(capabilitySelects).toHaveLength(3)
    for (const select of capabilitySelects) {
      expect(select).toHaveAttribute("data-slot", "select-trigger")
    }
    const visionSelect = capabilitySelects.at(0)
    expect(visionSelect).toBeDefined()
    if (!visionSelect) return
    await user.click(visionSelect)
    await user.click(screen.getByRole("option", { name: "?" }))
    expect(visionSelect).toHaveTextContent("?")
  }, 10_000)

  it("edits every row and saves one complete model list", async () => {
    const user = userEvent.setup()
    renderDialog()

    const dialog = screen.getByRole("dialog", { name: "OpenAI Main 的模型" })
    await user.click(within(dialog).getByRole("button", { name: "编辑全部" }))

    const displayInput = within(dialog).getByRole("textbox", { name: "显示名称 GPT Test" })
    await user.clear(displayInput)
    await user.type(displayInput, "GPT Test Updated")
    const firstModelRow = within(dialog).getAllByRole("row")[1]!
    const visionSelect = within(firstModelRow).getByRole("combobox", { name: "视觉" })
    await user.click(visionSelect)
    await user.click(screen.getByRole("option", { name: "?" }))
    await user.click(within(firstModelRow).getByRole("button", { name: "停用" }))
    await user.click(within(firstModelRow).getByRole("button", { name: "启用" }))
    await user.click(within(dialog).getByRole("button", { name: "保存全部" }))

    expect(saveProviderModels).toHaveBeenCalledTimes(1)
    expect(saveProviderModels).toHaveBeenCalledWith(
      "conn-openai",
      expect.arrayContaining([
        expect.objectContaining({ original_id: "gpt-test", display_name: "GPT Test Updated", supports_vision: null, hidden: false }),
        expect.objectContaining({ original_id: "manual-model", id: "manual-model", hidden: true }),
      ]),
      "csrf",
    )
  }, 10_000)

  it("keeps the editor open when the batch save fails", async () => {
    vi.mocked(saveProviderModels).mockRejectedValueOnce(new Error("save failed"))
    const user = userEvent.setup()
    renderDialog()

    const dialog = screen.getByRole("dialog", { name: "OpenAI Main 的模型" })
    await user.click(within(dialog).getByRole("button", { name: "编辑全部" }))
    const displayInput = within(dialog).getByRole("textbox", { name: "显示名称 GPT Test" })
    await user.clear(displayInput)
    await user.type(displayInput, "Unsaved name")
    await user.click(within(dialog).getByRole("button", { name: "保存全部" }))

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("模型信息没有保存")
    expect(within(dialog).getByRole("button", { name: "保存全部" })).toBeEnabled()
    expect(within(dialog).getByDisplayValue("Unsaved name")).toBeInTheDocument()
  }, 10_000)
})

function renderDialog(): void {
  const i18n = createI18n()
  document.documentElement.lang = "zh-CN"
  render(
    <I18nextProvider i18n={i18n}>
      <ToastProvider><ProviderModelsDialog connection={connection} csrfToken="csrf" onChanged={vi.fn(async () => undefined)} onOpenChange={vi.fn()} open /></ToastProvider>
    </I18nextProvider>,
  )
}
