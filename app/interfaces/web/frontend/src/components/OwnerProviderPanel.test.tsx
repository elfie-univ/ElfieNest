import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  changeProviderConnectionLifecycle,
  createProviderConnection,
  ownerProviderCatalog,
  ownerProviderConnections,
  updateProviderConnection,
  validateAllProviderModels,
  verifyProviderConnection,
  type ProviderConnection,
  type ProviderProduct,
} from "../api/owner-providers"
import { ApiError } from "../api/http"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
import { OwnerProviderPanel } from "./OwnerProviderPanel"

vi.mock("../api/owner-providers", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-providers")>()
  return {
    ...original,
    changeProviderConnectionLifecycle: vi.fn(),
    createProviderConnection: vi.fn(),
    ownerProviderCatalog: vi.fn(),
    ownerProviderConnections: vi.fn(),
    updateProviderConnection: vi.fn(),
    validateAllProviderModels: vi.fn(),
    verifyProviderConnection: vi.fn(),
  }
})

const product = {
  catalog_id: "openai",
  name: "OpenAI",
  brand: { brand_id: "openai", name: "OpenAI", logo_asset: "brands/openai.svg" },
  connection_method: "api_key",
  oauth_available: false,
  usage_scope: "remote",
  discovery_strategy: "remote",
  api_mode: "chat_completions",
} satisfies ProviderProduct

const ollamaProduct = {
  ...product,
  catalog_id: "ollama",
  name: "Ollama",
  brand: { brand_id: "ollama", name: "Ollama", logo_asset: "brands/ollama.svg" },
  connection_method: "local",
  usage_scope: "local",
  api_mode: "ollama",
} satisfies ProviderProduct

const model = {
  id: "gpt-test",
  display_name: "GPT Test",
  canonical_model_id: "gpt-test",
  source: "official",
  context_window_tokens: 128000,
  max_output_tokens: 4096,
  supports_tools: true,
  supports_vision: false,
  supports_reasoning: true,
  hidden: false,
  retired: false,
  available: true,
} as const

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
  models: [model],
  model_refresh: null,
} satisfies ProviderConnection

const ollamaConnection = {
  ...connection,
  connection_id: "conn-ollama",
  catalog_id: "ollama",
  alias: "Ollama",
  api_base: "http://localhost:11434",
  api_mode: "ollama",
  auth_type: "none",
  has_api_key: false,
  usage_scope: "local",
} satisfies ProviderConnection

describe("OwnerProviderPanel v2 behavior", () => {
  beforeEach(() => {
    vi.mocked(ownerProviderCatalog).mockResolvedValue([product])
    vi.mocked(ownerProviderConnections).mockResolvedValue([connection])
    vi.mocked(createProviderConnection).mockResolvedValue(connection)
    vi.mocked(updateProviderConnection).mockResolvedValue(connection)
    vi.mocked(changeProviderConnectionLifecycle).mockResolvedValue(connection)
    vi.mocked(validateAllProviderModels).mockResolvedValue({
      run_id: "validation-run",
      status: "passed",
      results: [{ subject: "conn-openai/gpt-test", status: "passed", checked_at: "2026-07-30T00:00:00Z" }],
    })
  })

  it("renders catalog and configured connections as separate actionable regions", async () => {
    renderPanel()

    const configured = await screen.findByRole("region", { name: "已配置的订阅" })
    const card = within(configured).getByRole("article")
    expect(within(card).getByRole("heading", { name: "OpenAI Main" })).toBeInTheDocument()
    expect(within(card).getByText("1 个可见模型")).toBeInTheDocument()

    const available = screen.getByRole("region", { name: "添加新的订阅" })
    expect(within(available).getByRole("button", { name: "配置 OpenAI" })).toBeInTheDocument()
    expect(within(available).getByRole("button", { name: "添加其他订阅" })).toBeInTheDocument()
    expect(within(available).queryByRole("button", { name: "添加自定义连接" })).not.toBeInTheDocument()
    expect(within(available).getByRole("button", { name: "配置 OpenAI" }).querySelector("img")).toHaveAttribute(
      "src",
      "/brands/openai.svg",
    )
  })

  it("does not repeat the configured Ollama in the add-subscription grid", async () => {
    vi.mocked(ownerProviderCatalog).mockResolvedValue([ollamaProduct, product])
    vi.mocked(ownerProviderConnections).mockResolvedValue([ollamaConnection, connection])
    renderPanel()

    const available = await screen.findByRole("region", { name: "添加新的订阅" })
    expect(within(available).queryByRole("button", { name: "配置 Ollama" })).not.toBeInTheDocument()
  })

  it("shows eight featured products and one add-other entry", async () => {
    const catalog = Array.from({ length: 10 }, (_, index) => ({
      ...product,
      catalog_id: `provider-${index}`,
      name: `Provider ${index + 1}`,
      brand: { ...product.brand, brand_id: `provider-${index}`, name: `Provider ${index + 1}`, logo_asset: "" },
    })) satisfies ProviderProduct[]
    vi.mocked(ownerProviderCatalog).mockResolvedValue(catalog)
    renderPanel()

    const available = await screen.findByRole("region", { name: "添加新的订阅" })
    expect(within(available).getAllByRole("button")).toHaveLength(9)
    expect(within(available).getAllByRole("button", { name: /^配置 Provider/ })).toHaveLength(8)
    expect(within(available).queryByText("api_key")).not.toBeInTheDocument()
  })

  it("verifies one connection and refreshes visible state", async () => {
    const user = userEvent.setup()
    renderPanel()

    const card = within(await screen.findByRole("region", { name: "已配置的订阅" })).getByRole("article")
    await user.click(within(card).getByRole("button", { name: "验证" }))

    expect(verifyProviderConnection).toHaveBeenCalledWith("conn-openai", "csrf")
    expect(await screen.findByText("OpenAI Main 验证已完成。")).toBeInTheDocument()
    expect(vi.mocked(ownerProviderConnections).mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it("creates a catalog connection through the product-specific form", async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.click(await screen.findByRole("button", { name: "配置 OpenAI" }))
    const dialog = screen.getByRole("dialog", { name: "配置 OpenAI" })
    await user.type(within(dialog).getByLabelText("API 密钥", { selector: "input" }), "secret")
    await user.click(within(dialog).getByRole("button", { name: "验证并保存" }))

    expect(createProviderConnection).toHaveBeenCalledWith(
      expect.objectContaining({ api_key: "secret", catalog_id: "openai", refresh_models: true, verify: true }),
      "csrf",
    )
  })

  it("archives an existing connection from the anchored lifecycle menu", async () => {
    const user = userEvent.setup()
    renderPanel()

    const card = within(await screen.findByRole("region", { name: "已配置的订阅" })).getByRole("article")
    await user.click(within(card).getByRole("button", { name: "更多" }))
    const menu = screen.getByRole("menu")
    expect(screen.queryByRole("dialog", { name: "更多操作" })).not.toBeInTheDocument()
    await user.click(within(menu).getByRole("menuitem", { name: "归档" }))

    expect(changeProviderConnectionLifecycle).toHaveBeenCalledWith("conn-openai", "archive", "csrf")
  })

  it("relocalizes a stored backend failure without losing the page", async () => {
    vi.mocked(ownerProviderConnections).mockRejectedValue(new ApiError(503, "后端失败"))
    const instance = renderPanel("zh-CN")
    expect(await screen.findByRole("alert")).toHaveTextContent("后端失败")

    await instance.changeLanguage("en-US")
    expect(screen.getByRole("heading", { name: "Providers and model connections" })).toBeInTheDocument()
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to load management data.")
    expect(screen.queryByText("后端失败")).not.toBeInTheDocument()
  })
})

function renderPanel(locale: SupportedLocale = "zh-CN"): ReturnType<typeof createI18n> {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  document.documentElement.lang = locale
  render(<I18nextProvider i18n={instance}><OwnerProviderPanel csrfToken="csrf" /></I18nextProvider>)
  return instance
}
