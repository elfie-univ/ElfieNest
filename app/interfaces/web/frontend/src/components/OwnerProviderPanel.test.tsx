import { fireEvent, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  addProviderModel,
  benchmarkProviderModels,
  createProviderConnection,
  ownerModelMatrix,
  ownerProviderCatalog,
  ownerProviderConnections,
  type ModelMatrix,
  type ProviderConnection,
  type ProviderProduct,
} from "../api/owner-providers"
import { OwnerProviderPanel } from "./OwnerProviderPanel"

vi.mock("../api/owner-providers", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-providers")>()
  return {
    ...original,
    addProviderModel: vi.fn(),
    benchmarkProviderModels: vi.fn(),
    createProviderConnection: vi.fn(),
    deleteProviderConnection: vi.fn(),
    deleteProviderModel: vi.fn(),
    ownerModelMatrix: vi.fn(),
    ownerProviderCatalog: vi.fn(),
    ownerProviderConnections: vi.fn(),
    refreshProviderModels: vi.fn(),
    updateProviderConnection: vi.fn(),
    updateProviderModel: vi.fn(),
    verifyProviderConnection: vi.fn(),
  }
})

const product = (catalogId: string, name: string, brandId = catalogId): ProviderProduct => ({
  catalog_id: catalogId,
  name,
  brand: { brand_id: brandId, name, logo_asset: `brands/${brandId}.svg` },
  connection_method: catalogId === "ollama" ? "local" : "api_key",
  oauth_available: false,
  usage_scope: catalogId === "ollama" ? "local" : "general",
  discovery_strategy: "standard_models",
  api_mode: catalogId === "ollama" ? "ollama" : "chat_completions",
})

const catalog = [
  product("ollama", "Ollama"),
  product("openai_api", "OpenAI", "openai"),
  product("anthropic_api", "Anthropic", "anthropic"),
  product("qwen_api", "Ali Qwen", "alibaba"),
  product("deepseek_api", "DeepSeek", "deepseek"),
  product("gemini_api", "Google Gemini", "google"),
  product("groq_api", "Groq", "groq"),
] satisfies readonly ProviderProduct[]

const model = {
  id: "qwen3:4b",
  display_name: "Qwen 3 4B",
  canonical_model_id: null,
  source: "discovered" as const,
  context_window_tokens: null,
  max_output_tokens: null,
  supports_tools: null,
  supports_vision: null,
  supports_reasoning: null,
  hidden: false,
}

const ollama = {
  connection_id: "ollama_0001",
  catalog_id: "ollama",
  alias: "Ollama",
  api_base: "http://localhost:11434",
  api_mode: "ollama",
  auth_type: "none",
  has_api_key: false,
  enabled: true,
  usage_scope: "local",
  verification: { status: "passed", checked_at: "2026-07-26T00:00:00Z", latency_ms: 12, error: null },
  models: [model],
  model_refresh: null,
} satisfies ProviderConnection

const openai = {
  ...ollama,
  connection_id: "openai_api_0001",
  catalog_id: "openai_api",
  alias: "工作账号",
  api_base: "https://api.openai.com/v1",
  api_mode: "chat_completions",
  auth_type: "bearer",
  has_api_key: true,
  usage_scope: "general",
  verification: { status: "never", checked_at: null, latency_ms: null, error: null },
  models: [{ ...model, id: "gpt-test", display_name: "GPT Test", source: "manual" as const }],
} satisfies ProviderConnection

const modelMatrix = {
  connections: [
    { connection_id: "ollama_0001", name: "Ollama", verification: ollama.verification },
    { connection_id: "openai_api_0001", name: "工作账号", verification: openai.verification },
  ],
  models: [{
    model_key: "qwen-3",
    display_name: "Qwen 3 4B",
    capabilities: ["text"],
    connections: [
      { connection_id: "ollama_0001", model_id: "qwen3:4b", available: true, verification_status: "passed", benchmark_status: "passed", latency_ms: 12, latency_class: "fast", price_estimate: null },
      { connection_id: "openai_api_0001", model_id: null, available: false, verification_status: "never", benchmark_status: null, latency_ms: null, latency_class: null, price_estimate: null },
    ],
  }],
} satisfies ModelMatrix

describe("OwnerProviderPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(ownerProviderCatalog).mockResolvedValue(catalog)
    vi.mocked(ownerProviderConnections).mockResolvedValue([openai, ollama])
    vi.mocked(ownerModelMatrix).mockResolvedValue(modelMatrix)
    vi.mocked(benchmarkProviderModels).mockResolvedValue({ results: [] })
  })

  it("shows configured connection instances and featured products separately", async () => {
    render(<OwnerProviderPanel csrfToken="csrf" />)

    const configured = await screen.findByRole("region", { name: "已配置的订阅" })
    const available = screen.getByRole("region", { name: "添加新的订阅" })
    expect(within(configured).getByRole("heading", { name: "Ollama" })).toBeInTheDocument()
    expect(within(configured).getByRole("heading", { name: "工作账号" })).toBeInTheDocument()
    expect(within(available).getByRole("button", { name: "配置 Anthropic" })).toBeInTheDocument()
    expect(within(available).getByRole("button", { name: "添加其他订阅" })).toBeInTheDocument()
  })

  it("keeps known-product setup to alias and API key", async () => {
    const user = userEvent.setup()
    render(<OwnerProviderPanel csrfToken="csrf" />)
    const available = await screen.findByRole("region", { name: "添加新的订阅" })
    await user.click(within(available).getByRole("button", { name: "配置 Anthropic" }))

    const dialog = screen.getByRole("dialog", { name: "配置 Anthropic" })
    expect(within(dialog).getByRole("textbox", { name: "订阅别名" })).toBeInTheDocument()
    expect(within(dialog).getByLabelText("API 密钥", { selector: "input" })).toHaveAttribute("type", "password")
    expect(within(dialog).queryByRole("textbox", { name: /ID|URL/ })).not.toBeInTheDocument()
    expect(within(dialog).queryByText("认证方式")).not.toBeInTheDocument()
  })

  it("creates a custom connection without asking for an internal id", async () => {
    const user = userEvent.setup()
    vi.mocked(createProviderConnection).mockResolvedValue(openai)
    render(<OwnerProviderPanel csrfToken="csrf" />)
    await screen.findByRole("region", { name: "添加新的订阅" })

    await user.click(screen.getByRole("button", { name: "添加自定义连接" }))
    const dialog = screen.getByRole("dialog", { name: "添加自定义连接" })
    expect(within(dialog).queryByRole("textbox", { name: /供应商 ID/ })).not.toBeInTheDocument()
    fireEvent.change(within(dialog).getByRole("textbox", { name: "显示名称" }), { target: { value: "京东" } })
    fireEvent.change(within(dialog).getByRole("textbox", { name: "API Base URL" }), { target: { value: "https://gateway.example/v1" } })
    fireEvent.change(within(dialog).getByLabelText("API 密钥", { selector: "input" }), { target: { value: "local-key" } })
    await user.click(within(dialog).getByRole("button", { name: "验证并保存" }))

    expect(createProviderConnection).toHaveBeenCalledWith(expect.objectContaining({
      catalog_id: "custom_openai",
      alias: "京东",
      api_base: "https://gateway.example/v1",
      api_key: "local-key",
    }), "csrf")
  })

  it("orders configured actions as models verify edit delete", async () => {
    render(<OwnerProviderPanel csrfToken="csrf" />)
    const configured = await screen.findByRole("region", { name: "已配置的订阅" })
    const card = within(configured).getByRole("heading", { name: "工作账号" }).closest("article")
    expect(card).not.toBeNull()
    if (!card) return
    expect(within(card).getAllByRole("button").map((button) => button.textContent)).toEqual([
      "查看模型", "验证", "修改", "删除",
    ])
  })

  it("opens the connection model panel and supports manual model input", async () => {
    const user = userEvent.setup()
    vi.mocked(addProviderModel).mockResolvedValue(openai.models[0]!)
    render(<OwnerProviderPanel csrfToken="csrf" />)
    await user.click(await screen.findByRole("button", { name: "查看 工作账号 的模型" }))
    const dialog = screen.getByRole("dialog", { name: "工作账号 的模型" })
    expect(within(dialog).getByRole("cell", { name: "gpt-test" })).toBeInTheDocument()
    await user.click(within(dialog).getByRole("button", { name: "手工添加模型" }))
    expect(within(dialog).getByRole("textbox", { name: "Model ID" })).toBeInTheDocument()
    expect(within(dialog).getByRole("button", { name: "高级参数" })).toBeInTheDocument()
  })
})
