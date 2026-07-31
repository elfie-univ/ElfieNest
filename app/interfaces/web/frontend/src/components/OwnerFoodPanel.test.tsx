import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import {
  changeFoodLifecycle,
  createFood,
  deleteFood,
  editFood,
  ownerFoods,
  previewFoodUpdate,
  type FoodCatalog,
  type FoodPackage,
} from "../api/owner-foods"
import { ownerProviderConnections, type ProviderConnection } from "../api/owner-providers"
import { ApiError } from "../api/http"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
import { OwnerFoodPanel } from "./OwnerFoodPanel"

vi.mock("../api/owner-foods", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-foods")>()
  return {
    ...original,
    changeFoodLifecycle: vi.fn(),
    createFood: vi.fn(),
    deleteFood: vi.fn(),
    editFood: vi.fn(),
    ownerFoods: vi.fn(),
    previewFoodUpdate: vi.fn(),
  }
})
vi.mock("../api/owner-providers", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-providers")>()
  return { ...original, ownerProviderConnections: vi.fn() }
})

const food = {
  key: "standard",
  display_name: "标准粮",
  system_role: "common",
  enabled: true,
  archived: false,
  roles: {
    primary: { model: "conn-local/qwen" },
    reasoning: { model: "conn-local/deepseek" },
    vision: null,
    tool: { model: "conn-local/qwen" },
    fallback: [{ model: "conn-remote/gpt" }],
  },
  health: "passed",
  locality: "mixed",
  latest_evidence_at: "2026-07-30T00:00:00Z",
} satisfies FoodPackage

const catalog = {
  version: 2,
  global_default_food_id: "standard",
  global_emergency_food_id: "emergency",
  packages: [food],
  eligible_models: [
    { reference: "conn-local/qwen", display_name: "Qwen", local: true, capabilities: ["text", "tools"] },
    { reference: "conn-local/deepseek", display_name: "DeepSeek", local: true, capabilities: ["text", "reasoning"] },
    { reference: "conn-remote/gpt", display_name: "GPT", local: false, capabilities: ["text"] },
  ],
} satisfies FoodCatalog

const connection = {
  connection_id: "conn-local",
  catalog_id: "ollama",
  alias: "Local Ollama",
  api_base: "http://127.0.0.1:11434",
  api_mode: "ollama",
  auth_type: "none",
  has_api_key: false,
  enabled: true,
  archived: false,
  usage_scope: "local",
  verification: { status: "passed", checked_at: "2026-07-30T00:00:00Z", latency_ms: 10, error: null },
  models: [],
  model_refresh: null,
} satisfies ProviderConnection

describe("OwnerFoodPanel v2 behavior", () => {
  beforeAll(() => {
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
  })

  beforeEach(() => {
    vi.mocked(ownerFoods).mockResolvedValue(catalog)
    vi.mocked(ownerProviderConnections).mockResolvedValue([connection])
    vi.mocked(editFood).mockResolvedValue({ food, warnings: [] })
    vi.mocked(changeFoodLifecycle).mockResolvedValue(food)
    vi.mocked(deleteFood).mockResolvedValue(catalog)
    vi.mocked(createFood).mockResolvedValue({ food, catalog })
    vi.mocked(previewFoodUpdate).mockResolvedValue({
      food_id: "standard",
      candidate: food,
      changes: [{ role: "reasoning", old_model: "conn-local/deepseek", new_model: "conn-local/qwen" }],
      warnings: [],
      has_changes: true,
    })
  })

  it("renders semantic roles and never exposes raw JSON", async () => {
    renderPanel()

    expect(await screen.findByRole("table", { name: "粮食套餐" })).toBeInTheDocument()
    const roles = screen.getByRole("table", { name: "标准粮角色配置" })
    expect(within(roles).getByRole("row", { name: /Primary.*conn-local\/qwen/ })).toBeInTheDocument()
    expect(within(roles).getByRole("row", { name: /Reasoning.*conn-local\/deepseek/ })).toBeInTheDocument()
    expect(within(roles).getByRole("row", { name: /Fallback.*conn-remote\/gpt/ })).toBeInTheDocument()
    expect(screen.queryByRole("textbox", { name: /JSON/i })).not.toBeInTheDocument()
  })

  it("edits and saves only the selected package", async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.click(await screen.findByRole("button", { name: "编辑" }))
    expect(screen.getByRole("textbox", { name: "套餐名称" })).toHaveValue("标准粮")
    await user.click(screen.getByRole("button", { name: "保存" }))

    expect(editFood).toHaveBeenCalledWith(
      "standard",
      expect.objectContaining({ display_name: "标准粮", roles: food.roles }),
      "csrf",
    )
  })

  it("generates an editable difference only from selected verified connections", async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.click(await screen.findByRole("button", { name: "自动生成" }))
    const dialog = screen.getByRole("dialog", { name: "自动生成 标准粮" })
    expect(within(dialog).getByText("Local Ollama")).toBeInTheDocument()
    await user.click(within(dialog).getByRole("button", { name: "生成差异" }))

    expect(previewFoodUpdate).toHaveBeenCalledWith("standard", ["conn-local"], false, true, "csrf")
    expect(await screen.findByText(/已生成 1 项差异/)).toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: "套餐名称" })).toHaveValue("标准粮")
  })

  it("changes lifecycle through the explicit state action", async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.click(await screen.findByRole("button", { name: "停用" }))
    expect(changeFoodLifecycle).toHaveBeenCalledWith("standard", "disable", "csrf")
  })

  it("keeps backend detail in Chinese and hides it after switching to English", async () => {
    vi.mocked(ownerFoods).mockRejectedValue(new ApiError(503, "后端失败"))
    const instance = renderPanel("zh-CN")
    expect(await screen.findByRole("alert")).toHaveTextContent("后端失败")

    await instance.changeLanguage("en-US")
    expect(screen.getByRole("heading", { name: "Food packages" })).toBeInTheDocument()
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to load management data.")
    expect(screen.queryByText("后端失败")).not.toBeInTheDocument()
  })
})

function renderPanel(locale: SupportedLocale = "zh-CN"): ReturnType<typeof createI18n> {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  document.documentElement.lang = locale
  render(<I18nextProvider i18n={instance}><OwnerFoodPanel csrfToken="csrf" /></I18nextProvider>)
  return instance
}
