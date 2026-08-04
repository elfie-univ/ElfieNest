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
  previewNewFood,
  type FoodCatalog,
  type FoodPackage,
} from "../api/owner-foods"
import { ownerProviderConnections, type ProviderConnection } from "../api/owner-providers"
import { ownerUsers, type OwnerUser } from "../api/owner-users"
import { ApiError } from "../api/http"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
import { OwnerFoodPanel } from "./OwnerFoodPanel"

vi.mock("../api/owner-foods", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-foods")>()
  return { ...original, changeFoodLifecycle: vi.fn(), createFood: vi.fn(), deleteFood: vi.fn(), editFood: vi.fn(), ownerFoods: vi.fn(), previewFoodUpdate: vi.fn(), previewNewFood: vi.fn() }
})
vi.mock("../api/owner-providers", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-providers")>()
  return { ...original, ownerProviderConnections: vi.fn() }
})
vi.mock("../api/owner-users", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-users")>()
  return { ...original, ownerUsers: vi.fn() }
})

const food = {
  key: "standard",
  display_name: "标准粮",
  system_role: "common",
  enabled: true,
  archived: false,
  visibility_mode: "global",
  visible_user_ids: [],
  roles: {
    primary: { model: "conn-local/qwen" },
    reasoning: { model: "conn-local/deepseek" },
    vision: null,
    tool: { model: "conn-local/qwen" },
    fallback: { model: "conn-remote/gpt" },
  },
  health: "healthy",
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
  models: [
    { id: "qwen", display_name: "Qwen 0.5B", canonical_model_id: null, source: "manual", context_window_tokens: 8192, max_output_tokens: 2048, supports_tools: true, supports_vision: false, supports_reasoning: false, hidden: false, retired: false, available: true, verification: { status: "passed", checked_at: "2026-07-30T00:00:00Z", latency_ms: 120, error: null } },
    { id: "deepseek", display_name: "DeepSeek", canonical_model_id: null, source: "manual", context_window_tokens: 8192, max_output_tokens: 2048, supports_tools: false, supports_vision: false, supports_reasoning: true, hidden: false, retired: false, available: true, verification: { status: "passed", checked_at: "2026-07-30T00:00:00Z", latency_ms: 180, error: null } },
  ],
  model_refresh: null,
} satisfies ProviderConnection

const secondConnection = { ...connection, connection_id: "conn-remote", alias: "Remote Gateway" }
const thirdConnection = { ...connection, connection_id: "conn-third", alias: "Third Gateway" }
const members = [
  { user_id: 2, account_id: "alice", display_name: "张三", role: "user", presence: "offline" },
  { user_id: 3, account_id: "bob", display_name: "李四", role: "user", presence: "offline" },
].map((user) => ({
  ...user,
  gender: null,
  birth_date: null,
  last_seen_at: null,
  language: "zh-CN",
  created_at: "2026-07-30T00:00:00Z",
  elfie_count: 0,
  elfie_quota_override: null,
  effective_elfie_limit: 4,
  avatar_url: null,
})) as OwnerUser[]

describe("OwnerFoodPanel final list behavior", () => {
  beforeAll(() => {
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
  })

  beforeEach(() => {
    vi.mocked(ownerFoods).mockResolvedValue(catalog)
    vi.mocked(ownerProviderConnections).mockResolvedValue([connection])
    vi.mocked(ownerUsers).mockResolvedValue([])
    vi.mocked(editFood).mockResolvedValue({ food, warnings: [] })
    vi.mocked(changeFoodLifecycle).mockResolvedValue(food)
    vi.mocked(deleteFood).mockResolvedValue(catalog)
    vi.mocked(createFood).mockResolvedValue({ food, catalog })
    vi.mocked(previewFoodUpdate).mockResolvedValue({ food_id: "standard", candidate: { display_name: "标准粮", enabled: true, roles: food.roles }, changes: [{ role: "reasoning", old_model: "conn-local/deepseek", new_model: "conn-local/qwen" }], warnings: [], has_changes: true })
    vi.mocked(previewNewFood).mockResolvedValue({ food_id: null, candidate: { display_name: "新粮食", enabled: true, roles: { ...food.roles, primary: { model: "conn-local/qwen" } } }, changes: [{ role: "primary", old_model: null, new_model: "conn-local/qwen" }], warnings: [], has_changes: true })
  })

  it("renders exactly the flat nine-column list and human-readable model cells", async () => {
    renderPanel()
    const table = await screen.findByRole("table", { name: "粮食套餐" })
    expect(within(table).getAllByRole("columnheader")).toHaveLength(9)
    expect(within(table).getAllByText(/Qwen 0\.5B/).length).toBeGreaterThan(0)
    expect(within(table).getByText("运行中")).toBeInTheDocument()
    expect(screen.queryByRole("table", { name: "标准粮角色配置" })).not.toBeInTheDocument()
  })

  it("does not create an empty food and only creates after preview confirmation", async () => {
    const user = userEvent.setup()
    renderPanel()
    await user.click(await screen.findByRole("button", { name: "添加粮食" }))
    const dialog = screen.getByRole("dialog", { name: "添加粮食" })
    expect(createFood).not.toHaveBeenCalled()
    await user.type(within(dialog).getByRole("textbox", { name: "粮食名称" }), "新粮食")
    await user.click(within(dialog).getByRole("button", { name: "生成预览" }))
    expect(previewNewFood).toHaveBeenCalled()
    expect(createFood).not.toHaveBeenCalled()
    await user.click(within(dialog).getByRole("button", { name: "保存创建" }))
    expect(createFood).toHaveBeenCalledWith(expect.objectContaining({
      display_name: "新粮食",
      visibility_mode: "global",
      visible_user_ids: [],
    }), "csrf")
  })

  it("shares the update preview dialog and applies only after the candidate is reviewed", async () => {
    const user = userEvent.setup()
    renderPanel()
    await user.click(await screen.findByRole("button", { name: "操作" }))
    await user.click(screen.getByRole("menuitem", { name: "自动更新" }))
    const dialog = screen.getByRole("dialog", { name: "自动更新 标准粮" })
    await user.click(within(dialog).getByRole("button", { name: "生成预览" }))
    expect(await within(dialog).findByText("候选差异")).toBeInTheDocument()
    expect(within(dialog).getAllByText(/Local Ollama \/ Qwen 0\.5B/).length).toBeGreaterThan(0)
    expect(within(dialog).getAllByText("推理模型").length).toBeGreaterThan(0)
    expect(editFood).not.toHaveBeenCalled()
    await user.click(within(dialog).getByRole("button", { name: "应用更新" }))
    expect(editFood).toHaveBeenCalledWith("standard", expect.objectContaining({ display_name: "标准粮", visibility_mode: "global", visible_user_ids: [] }), "csrf")
  })

  it("keeps lifecycle actions inside the operation menu", async () => {
    const user = userEvent.setup()
    renderPanel()
    await user.click(await screen.findByRole("button", { name: "操作" }))
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "自动更新",
      "编辑",
      "停用",
    ])
    await user.click(screen.getByRole("menuitem", { name: "停用" }))
    expect(changeFoodLifecycle).toHaveBeenCalledWith("standard", "disable", "csrf")
  })

  it("keeps source and visibility choices compact across all, partial, none, and selected states", async () => {
    const user = userEvent.setup()
    vi.mocked(ownerProviderConnections).mockResolvedValue([connection, secondConnection, thirdConnection])
    vi.mocked(ownerUsers).mockResolvedValue(members)
    renderPanel()
    await user.click(await screen.findByRole("button", { name: "添加粮食" }))
    const dialog = screen.getByRole("dialog", { name: "添加粮食" })

    expect(within(dialog).getByRole("button", { name: "生成来源" })).toHaveTextContent("全部可用订阅（3）")
    await user.click(within(dialog).getByRole("button", { name: "生成来源" }))
    const sourcePopover = screen.getByRole("dialog", { name: "生成来源" })
    const sourceChecks = within(sourcePopover).getAllByRole("checkbox")
    await user.click(sourceChecks[1]!)
    expect(within(dialog).getByRole("button", { name: "生成来源" })).toHaveTextContent("Remote Gateway、Third Gateway")
    await user.click(within(sourcePopover).getAllByRole("checkbox")[0]!)
    expect(within(dialog).getByRole("button", { name: "生成来源" })).toHaveTextContent("未选择生成来源")
    expect(within(dialog).getByRole("button", { name: "生成预览" })).toBeDisabled()
    await user.click(within(sourcePopover).getAllByRole("checkbox")[0]!)

    await user.click(within(dialog).getByRole("button", { name: "可见范围" }))
    const visibilityPopover = screen.getByRole("dialog", { name: "可见范围" })
    await user.click(within(visibilityPopover).getByRole("radio", { name: "指定用户" }))
    const userChecks = within(visibilityPopover).getAllByRole("checkbox")
    await user.click(userChecks[0]!)
    expect(within(dialog).getByRole("button", { name: "可见范围" })).toHaveTextContent("指定用户：张三")
    await user.click(userChecks[1]!)
    expect(within(dialog).getByRole("button", { name: "可见范围" })).toHaveTextContent("指定用户：当前 2 人")
    await user.click(within(visibilityPopover).getByRole("radio", { name: "所有人可见" }))
    expect(within(dialog).getByRole("button", { name: "可见范围" })).toHaveTextContent("所有人可见")
    await user.click(within(visibilityPopover).getByRole("radio", { name: "指定用户" }))
    expect(within(visibilityPopover).getAllByRole("checkbox").every((checkbox) => !(checkbox as HTMLInputElement).checked)).toBe(true)
    const userSearch = within(visibilityPopover).getByRole("textbox", { name: "搜索用户" })
    await user.type(userSearch, "张")
    expect(within(visibilityPopover).getAllByRole("checkbox")).toHaveLength(1)
  })

  it("keeps the preview while visibility changes and blocks an empty user scope", async () => {
    const user = userEvent.setup()
    vi.mocked(ownerProviderConnections).mockResolvedValue([connection, secondConnection])
    vi.mocked(ownerUsers).mockResolvedValue(members)
    renderPanel()
    await user.click(await screen.findByRole("button", { name: "添加粮食" }))
    const dialog = screen.getByRole("dialog", { name: "添加粮食" })
    await user.type(within(dialog).getByRole("textbox", { name: "粮食名称" }), "范围粮")
    await user.click(within(dialog).getByRole("button", { name: "生成预览" }))
    expect(await within(dialog).findByText("候选差异")).toBeInTheDocument()

    await user.click(within(dialog).getByRole("button", { name: "可见范围" }))
    const visibilityPopover = screen.getByRole("dialog", { name: "可见范围" })
    await user.click(within(visibilityPopover).getByRole("radio", { name: "指定用户" }))
    expect(within(dialog).getByRole("button", { name: "保存创建" })).toBeDisabled()
    expect(within(dialog).getByText("候选差异")).toBeInTheDocument()
    await user.click(within(visibilityPopover).getAllByRole("checkbox")[0]!)
    expect(within(dialog).getByRole("button", { name: "保存创建" })).toBeEnabled()
    expect(within(dialog).getByText("候选差异")).toBeInTheDocument()
  })

  it("closes a compact scope menu with Escape and outside click", async () => {
    const user = userEvent.setup()
    renderPanel()
    await user.click(await screen.findByRole("button", { name: "添加粮食" }))
    const dialog = screen.getByRole("dialog", { name: "添加粮食" })
    const sourceTrigger = within(dialog).getByRole("button", { name: "生成来源" })
    await user.click(sourceTrigger)
    expect(document.querySelector('[role="dialog"][aria-label="生成来源"]')).toBeInTheDocument()
    await user.keyboard("{Escape}")
    expect(document.querySelector('[role="dialog"][aria-label="生成来源"]')).toBeNull()
    await user.click(sourceTrigger)
    const dialogTitle = dialog.querySelector('[data-slot="dialog-title"]')
    expect(dialogTitle).not.toBeNull()
    await user.click(dialogTitle!)
    expect(document.querySelector('[role="dialog"][aria-label="生成来源"]')).toBeNull()
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
