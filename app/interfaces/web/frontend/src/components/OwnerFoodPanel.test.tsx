import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import {
  applyFoodUpdate,
  editFood,
  ownerFoods,
  previewFoodUpdate,
  rollbackFoods,
  type FoodCatalog,
  type FoodPreview,
} from "../api/owner-foods"
import { ownerProviders } from "../api/owner-providers"
import { ApiError } from "../api/http"
import { OwnerFoodPanel } from "./OwnerFoodPanel"

vi.mock("../api/owner-foods", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-foods")>()
  return {
    ...original,
    applyFoodUpdate: vi.fn(),
    editFood: vi.fn(),
    ownerFoods: vi.fn(),
    previewFoodUpdate: vi.fn(),
    rollbackFoods: vi.fn(),
  }
})
vi.mock("../api/owner-providers", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-providers")>()
  return { ...original, ownerProviders: vi.fn() }
})

const profile = (model: string, reasoning = "balanced") => ({
  model,
  reasoning_profile: reasoning,
  max_tokens: 1500,
  temperature: 0.7,
  provider_options: {},
})
const standardFood = {
  key: "standard",
  display_name: "标准粮",
  description: "日常默认",
  primary: profile("ollama/primary"),
  deep: profile("ollama/deep", "deep"),
  vision: null,
  verifier: profile("ollama/verifier", "verify"),
  technical_fallbacks: [profile("ollama/fallback", "low")],
  local_only: true,
  validation_status: "passed",
  source: "manual",
  locked_fields: [],
}
const catalog = {
  version: 2,
  default_food: "standard",
  fallback_food: "",
  source_fingerprint: "current",
  generated_at: "2026-07-26T00:00:00Z",
  generation_sources: ["manual"],
  generation_note: "",
  foods: { standard: standardFood },
} satisfies FoodCatalog
const candidate = {
  ...catalog,
  version: 3,
  source_fingerprint: "candidate",
  foods: {
    standard: {
      ...standardFood,
      primary: profile("ollama/new-primary"),
      verifier: profile("ollama/new-verifier", "verify"),
      source: "auto",
    },
  },
} satisfies FoodCatalog
const preview = {
  has_changes: true,
  base_catalog_fingerprint: "current-catalog-fingerprint",
  generation_sources: ["rules"],
  advisor_error: null,
  warnings: [],
  changes: [{
    food_key: "standard",
    change_type: "updated",
    old_model: "ollama/primary",
    new_model: "ollama/new-primary",
    warnings: [],
  }],
  current: catalog,
  candidate,
} satisfies FoodPreview
const configuredProviders = [{
  provider_id: "ollama",
  name: "Ollama",
  display_name: "Ollama 本地",
  api_base: "http://127.0.0.1:11434",
  api_mode: "ollama",
  auth_type: "none",
  test_model: "llama3",
  configured: true,
  configuration_status: "configured" as const,
  verification: { status: "passed" as const, checked_at: null, latency_ms: null, error: null },
  has_api_key: false,
  models: [
    { id: "primary", display_name: "Primary", source: "configured" as const },
    { id: "deep", display_name: "Deep", source: "configured" as const },
  ],
  model_refresh: {},
  capabilities: {
    connection_method: "local" as const,
    oauth_available: false,
    oauth_unavailable: false,
    model_discovery: true,
  },
}]

describe("OwnerFoodPanel", () => {
  beforeAll(() => {
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
  })

  beforeEach(() => {
    vi.mocked(ownerFoods).mockResolvedValue(catalog)
    vi.mocked(ownerProviders).mockResolvedValue(configuredProviders)
    vi.mocked(previewFoodUpdate).mockResolvedValue(preview)
    vi.mocked(applyFoodUpdate).mockResolvedValue(candidate)
    vi.mocked(editFood).mockResolvedValue({ food: standardFood, warnings: [] })
    vi.mocked(rollbackFoods).mockResolvedValue(catalog)
  })

  it("expands all execution roles without exposing JSON", async () => {
    const user = userEvent.setup()
    render(<OwnerFoodPanel csrfToken="csrf" />)

    await user.click(await screen.findByRole("button", { name: "展开 标准粮" }))

    const roles = screen.getByRole("table", { name: "标准粮角色配置" })
    expect(within(roles).getByRole("row", { name: /主模型.*ollama\/primary/ })).toBeInTheDocument()
    expect(within(roles).getByRole("row", { name: /深度模型.*ollama\/deep/ })).toBeInTheDocument()
    expect(within(roles).getByRole("row", { name: /校验模型.*ollama\/verifier/ })).toBeInTheDocument()
    expect(within(roles).getByRole("row", { name: /技术回退 1.*ollama\/fallback/ })).toBeInTheDocument()
    expect(screen.queryByRole("textbox", { name: /JSON/i })).not.toBeInTheDocument()
  })

  it("edits only the selected recipe inline through grouped role controls", async () => {
    const user = userEvent.setup()
    render(<OwnerFoodPanel csrfToken="csrf" />)

    await user.click(await screen.findByRole("button", { name: "编辑 标准粮" }))
    expect(screen.queryByRole("dialog", { name: "编辑 标准粮" })).not.toBeInTheDocument()
    const inlineEditor = screen.getByRole("group", { name: "编辑 标准粮" })
    expect(within(inlineEditor).getByRole("combobox", { name: "主模型" })).toBeInTheDocument()
    expect(within(inlineEditor).getByRole("combobox", { name: "深度模型" })).toBeInTheDocument()
    expect(within(inlineEditor).getByRole("combobox", { name: "校验模型" })).toBeInTheDocument()
    expect(within(inlineEditor).getByRole("button", { name: "添加技术回退" })).toBeInTheDocument()

    await user.click(within(inlineEditor).getByRole("combobox", { name: "主模型" }))
    expect(await screen.findByText("Ollama 本地")).toBeInTheDocument()
    await user.click(screen.getByRole("option", { name: "Ollama 本地 · Primary" }))

    await user.click(within(inlineEditor).getByRole("button", { name: "保存标准粮" }))

    expect(vi.mocked(editFood)).toHaveBeenCalledWith("standard", expect.objectContaining({ key: "standard" }), "csrf")
  }, 10_000)

  it("keeps food page actions in the header action slot", async () => {
    render(<OwnerFoodPanel csrfToken="csrf" />)

    const page = await screen.findByRole("region", { name: "粮食策略管理" })
    const header = within(page).getByRole("group", { name: "粮食页面动作" })

    expect(within(header).getByRole("button", { name: "重新读取" })).toBeInTheDocument()
    expect(within(header).getByRole("button", { name: "生成更新预览" })).toBeInTheDocument()
    expect(within(header).getByRole("button", { name: "回滚最近版本" })).toBeInTheDocument()
  })

  it("keeps generated changes in a diff preview until explicit confirmation", async () => {
    const user = userEvent.setup()
    render(<OwnerFoodPanel csrfToken="csrf" />)

    await user.click(await screen.findByRole("button", { name: "生成更新预览" }))

    const diff = screen.getByRole("dialog", { name: "粮食更新预览" })
    expect(within(diff).getByText("ollama/primary → ollama/new-primary")).toBeInTheDocument()
    expect(within(diff).getByText("ollama/verifier → ollama/new-verifier")).toBeInTheDocument()
    expect(vi.mocked(applyFoodUpdate)).not.toHaveBeenCalled()

    await user.click(within(diff).getByRole("button", { name: "继续应用" }))
    await user.click(screen.getByRole("button", { name: "确认应用" }))

    expect(vi.mocked(applyFoodUpdate)).toHaveBeenCalledWith(preview, "csrf")
  })

  it("restores focus to the preview trigger when the diff closes", async () => {
    const user = userEvent.setup()
    render(<OwnerFoodPanel csrfToken="csrf" />)

    const trigger = await screen.findByRole("button", { name: "生成更新预览" })
    await user.click(trigger)
    await user.click(screen.getByRole("button", { name: "关闭预览" }))

    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it("discards an expired candidate and requires a fresh preview", async () => {
    const user = userEvent.setup()
    vi.mocked(applyFoodUpdate).mockRejectedValueOnce(new ApiError(409, "candidate stale"))
    render(<OwnerFoodPanel csrfToken="csrf" />)

    await user.click(await screen.findByRole("button", { name: "生成更新预览" }))
    await user.click(screen.getByRole("button", { name: "继续应用" }))
    await user.click(screen.getByRole("button", { name: "确认应用" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("粮食候选已过期，请重新生成预览。")
    expect(screen.queryByRole("dialog", { name: "粮食更新预览" })).not.toBeInTheDocument()
  })
})
