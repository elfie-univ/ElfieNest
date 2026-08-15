import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  changeProviderConnectionLifecycle,
  completeProviderOAuthLogin,
  createProviderConnection,
  ownerProviderCatalog,
  ownerProviderConnections,
  startProviderOAuthLogin,
  updateProviderConnection,
  validateAllProviderModels,
  verifyProviderConnection,
  type ProviderConnection,
  type ProviderProduct,
} from "../api/owner-providers"
import {
  installOllama,
  ownerOllamaStatus,
  pullOllamaModels,
  startOllama,
  type OllamaStatus,
} from "../api/owner-ollama"
import { ApiError } from "../api/http"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
import { OwnerProviderPanel } from "./OwnerProviderPanel"
import { ToastProvider } from "./ui/toast"

vi.mock("../api/owner-providers", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-providers")>()
  return {
    ...original,
    changeProviderConnectionLifecycle: vi.fn(),
    completeProviderOAuthLogin: vi.fn(),
    createProviderConnection: vi.fn(),
    ownerProviderCatalog: vi.fn(),
    ownerProviderConnections: vi.fn(),
    startProviderOAuthLogin: vi.fn(),
    updateProviderConnection: vi.fn(),
    validateAllProviderModels: vi.fn(),
    verifyProviderConnection: vi.fn(),
  }
})

vi.mock("../api/owner-ollama", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-ollama")>()
  return {
    ...original,
    installOllama: vi.fn(),
    ownerOllamaStatus: vi.fn(),
    pullOllamaModels: vi.fn(),
    startOllama: vi.fn(),
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

const chatGptProduct = {
  ...product,
  catalog_id: "openai_chatgpt",
  name: "OpenAI (ChatGPT)",
  connection_method: "oauth",
  oauth_available: true,
  discovery_strategy: "catalog_only",
  api_mode: "codex_responses",
} satisfies ProviderProduct

const googleProduct = {
  ...product,
  catalog_id: "gemini_api",
  name: "Google Gemini",
  brand: { brand_id: "google", name: "Google", logo_asset: "brands/google.svg" },
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
  verification: { status: "passed", checked_at: "2026-07-30T00:00:00Z", latency_ms: 42, error: null },
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

const absentOllama = {
  state: "absent",
  endpoint: null,
  version: null,
  memory_gb: 16,
  recommended_model: "qwen2.5:0.5b",
  installed_model_count: 0,
  models: [],
  task: null,
} satisfies OllamaStatus

const stoppedOllama = {
  ...absentOllama,
  state: "stopped",
  endpoint: "http://127.0.0.1:11434",
  models: [{ id: "qwen2.5:0.5b", display_name: "qwen2.5:0.5b", installed: true, recommended: true }],
  installed_model_count: 1,
} satisfies OllamaStatus

const healthyOllama = {
  ...stoppedOllama,
  state: "healthy",
  version: "0.12.0",
  models: [
    { id: "qwen2.5:0.5b", display_name: "qwen2.5:0.5b", installed: true, recommended: true },
    { id: "qwen3.5:0.8b", display_name: "qwen3.5:0.8b", installed: false, recommended: false },
    { id: "gemma3:270m", display_name: "gemma3:270m", installed: false, recommended: false },
  ],
} satisfies OllamaStatus

describe("OwnerProviderPanel v2 behavior", () => {
  beforeEach(() => {
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
    vi.mocked(ownerProviderCatalog).mockResolvedValue([product])
    vi.mocked(ownerProviderConnections).mockResolvedValue([connection])
    vi.mocked(createProviderConnection).mockResolvedValue(connection)
    vi.mocked(updateProviderConnection).mockResolvedValue(connection)
    vi.mocked(changeProviderConnectionLifecycle).mockResolvedValue(connection)
    vi.mocked(ownerOllamaStatus).mockResolvedValue(absentOllama)
    vi.mocked(installOllama).mockResolvedValue(absentOllama)
    vi.mocked(startOllama).mockResolvedValue(stoppedOllama)
    vi.mocked(pullOllamaModels).mockResolvedValue(healthyOllama)
    vi.mocked(validateAllProviderModels).mockResolvedValue({
      run_id: "validation-run",
      status: "passed",
      results: [{ subject: "conn-openai/gpt-test", status: "passed", checked_at: "2026-07-30T00:00:00Z" }],
    })
  })

  it("authorizes a ChatGPT subscription through device login", async () => {
    const user = userEvent.setup()
    const oauthConnection = {
      ...connection,
      connection_id: "openai_chatgpt_0001",
      catalog_id: "openai_chatgpt",
      alias: "My ChatGPT",
      api_base: "https://chatgpt.com/backend-api/codex",
      api_mode: "codex_responses",
      has_api_key: false,
      has_credential: true,
    } satisfies ProviderConnection
    vi.mocked(ownerProviderCatalog).mockResolvedValue([product, chatGptProduct])
    vi.mocked(ownerProviderConnections)
      .mockResolvedValueOnce([])
      .mockResolvedValue([oauthConnection])
    vi.mocked(startProviderOAuthLogin).mockResolvedValue({
      catalog_id: "openai_chatgpt",
      login_id: "login-1",
      authorization_url: "https://auth.openai.com/codex/device",
      user_code: "ABCD-1234",
      poll_interval_seconds: 0,
      expires_at: "2026-08-13T12:10:00Z",
    })
    vi.mocked(completeProviderOAuthLogin).mockResolvedValue({
      catalog_id: "openai_chatgpt",
      login_id: "login-1",
      state: "completed",
      account_id: "account-1",
      expires_at: "2026-08-13T13:00:00Z",
      connection: oauthConnection,
    })
    renderPanel()
    await user.click(await screen.findByRole("button", { name: "配置 OpenAI" }))
    const chooseDialog = screen.getByRole("dialog", { name: "配置 OpenAI" })
    await user.click(within(chooseDialog).getByRole("combobox", { name: "连接方式" }))
    await user.click(screen.getByRole("option", { name: "ChatGPT 账号授权（订阅）" }))
    await user.click(within(chooseDialog).getByRole("button", { name: "继续" }))
    await user.click(screen.getByRole("button", { name: "使用 OpenAI 账号登录" }))

    await waitFor(() => expect(completeProviderOAuthLogin).toHaveBeenCalled())
    expect(startProviderOAuthLogin).toHaveBeenCalledWith("openai_chatgpt", "csrf")
    expect(await screen.findByRole("heading", { name: "My ChatGPT" })).toBeInTheDocument()
  })

  it("shows and copies the device code before the user opens authorization", async () => {
    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    })
    vi.mocked(ownerProviderCatalog).mockResolvedValue([product, chatGptProduct])
    vi.mocked(ownerProviderConnections).mockResolvedValue([])
    vi.mocked(startProviderOAuthLogin).mockResolvedValue({
      catalog_id: "openai_chatgpt",
      login_id: "login-1",
      authorization_url: "https://auth.openai.com/codex/device",
      user_code: "ABCD-1234",
      poll_interval_seconds: 60,
      expires_at: "2026-08-13T12:10:00Z",
    })
    const open = vi.spyOn(window, "open").mockReturnValue(null)

    renderPanel()
    await user.click(await screen.findByRole("button", { name: "配置 OpenAI" }))
    const dialog = screen.getByRole("dialog", { name: "配置 OpenAI" })
    await user.click(within(dialog).getByRole("combobox", { name: "连接方式" }))
    await user.click(screen.getByRole("option", { name: "ChatGPT 账号授权（订阅）" }))
    await user.click(within(dialog).getByRole("button", { name: "继续" }))
    await user.click(within(dialog).getByRole("button", { name: "使用 OpenAI 账号登录" }))

    expect(await within(dialog).findByText("ABCD-1234")).toBeInTheDocument()
    expect(within(dialog).getByText("实验性候选目录：模型不是从账号实时读取，将按账号逐个验证。")).toBeInTheDocument()
    expect(open).not.toHaveBeenCalled()
    await user.click(within(dialog).getByRole("button", { name: "复制授权码" }))
    expect(writeText).toHaveBeenCalledWith("ABCD-1234")
    await user.click(within(dialog).getByRole("link", { name: "打开 OpenAI 授权页" }))
    await user.click(within(dialog).getByRole("button", { name: "取消等待" }))
    expect(within(dialog).getByRole("button", { name: "重新生成授权码" })).toBeInTheDocument()
  })

  it("renders catalog and configured connections as separate actionable regions", async () => {
    renderPanel()

    const configured = await screen.findByRole("region", { name: "已配置的远程订阅" })
    const card = within(configured).getByRole("article")
    expect(within(card).getByRole("heading", { name: "OpenAI Main" })).toBeInTheDocument()
    expect(within(card).getByText("共 1 个模型（已启用 1 个 · 验证通过 1 个）")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "同模型对比" })).toBeInTheDocument()

    const available = screen.getByRole("region", { name: "添加新的远程订阅" })
    expect(within(available).getByRole("button", { name: "配置 OpenAI" })).toBeInTheDocument()
    expect(within(available).getByRole("button", { name: "添加其他订阅" })).toBeInTheDocument()
    expect(within(available).queryByRole("button", { name: "添加自定义连接" })).not.toBeInTheDocument()
    expect(within(available).getByRole("button", { name: "配置 OpenAI" }).querySelector("img")).toHaveAttribute(
      "src",
      "/brands/openai.svg",
    )
  })

  it("renders one company card when a brand offers multiple connection methods", async () => {
    vi.mocked(ownerProviderCatalog).mockResolvedValue([product, chatGptProduct])
    renderPanel()

    const available = await screen.findByRole("region", { name: "添加新的远程订阅" })
    expect(within(available).getAllByRole("button", { name: "配置 OpenAI" })).toHaveLength(1)
    expect(within(available).queryByRole("button", { name: "配置 OpenAI (ChatGPT)" })).not.toBeInTheDocument()
  })

  it("does not repeat the configured Ollama in the add-subscription grid", async () => {
    vi.mocked(ownerProviderCatalog).mockResolvedValue([ollamaProduct, product])
    vi.mocked(ownerProviderConnections).mockResolvedValue([ollamaConnection, connection])
    renderPanel()

    const available = await screen.findByRole("region", { name: "添加新的远程订阅" })
    expect(within(available).queryByRole("button", { name: "配置 Ollama" })).not.toBeInTheDocument()
  })

  it("shows the eight priority brands and one add-other entry", async () => {
    const catalog = [
      { ...product, catalog_id: "xai_api", name: "xAI", brand: { ...product.brand, brand_id: "xai", name: "xAI", logo_asset: "" } },
      { ...product, catalog_id: "qwen_api", name: "Qwen", brand: { ...product.brand, brand_id: "alibaba", name: "Alibaba Cloud", logo_asset: "" } },
      chatGptProduct,
      { ...product, catalog_id: "minimax_api", name: "MiniMax", brand: { ...product.brand, brand_id: "minimax", name: "MiniMax", logo_asset: "" } },
      { ...product, catalog_id: "gemini_api", name: "Gemini", brand: { ...product.brand, brand_id: "google", name: "Google", logo_asset: "" } },
      product,
      { ...product, catalog_id: "kimi_api", name: "Kimi", brand: { ...product.brand, brand_id: "moonshot", name: "Kimi", logo_asset: "" } },
      { ...product, catalog_id: "deepseek_api", name: "DeepSeek", brand: { ...product.brand, brand_id: "deepseek", name: "DeepSeek", logo_asset: "" } },
      { ...product, catalog_id: "anthropic_api", name: "Anthropic", brand: { ...product.brand, brand_id: "anthropic", name: "Anthropic", logo_asset: "" } },
      { ...product, catalog_id: "glm_api", name: "GLM", brand: { ...product.brand, brand_id: "zhipu", name: "Zhipu AI", logo_asset: "" } },
    ] satisfies ProviderProduct[]
    vi.mocked(ownerProviderCatalog).mockResolvedValue(catalog)
    renderPanel()

    const available = await screen.findByRole("region", { name: "添加新的远程订阅" })
    expect(within(available).getAllByRole("button")).toHaveLength(9)
    for (const name of ["Google", "OpenAI", "Anthropic", "DeepSeek", "Alibaba Cloud", "Zhipu AI", "Kimi", "MiniMax"]) {
      expect(within(available).getByRole("button", { name: `配置 ${name}` })).toBeInTheDocument()
    }
    expect(within(available).queryByRole("button", { name: "配置 xAI" })).not.toBeInTheDocument()
  })

  it("pins custom interfaces above the non-featured provider list", async () => {
    const user = userEvent.setup()
    const catalog = [
      ...Array.from({ length: 8 }, (_, index) => ({
        ...product,
        catalog_id: `provider-${index}`,
        name: `Provider ${index + 1}`,
        brand: { ...product.brand, brand_id: `provider-${index}`, name: `Provider ${index + 1}`, logo_asset: "" },
      })),
      { ...product, catalog_id: "provider-extra-1", name: "Provider Extra 1", brand: { ...product.brand, brand_id: "provider-extra-1", name: "Provider Extra 1", logo_asset: "" } },
      { ...product, catalog_id: "provider-extra-2", name: "Provider Extra 2", brand: { ...product.brand, brand_id: "provider-extra-2", name: "Provider Extra 2", logo_asset: "" } },
      { ...product, catalog_id: "custom_openai", name: "自定义 OpenAI 兼容接口", brand: { ...product.brand, brand_id: "custom", name: "Custom", logo_asset: "" } },
    ] satisfies ProviderProduct[]
    vi.mocked(ownerProviderCatalog).mockResolvedValue(catalog)
    renderPanel()

    await user.click(await screen.findByRole("button", { name: "添加其他订阅" }))
    const dialog = screen.getByRole("dialog", { name: "添加其他订阅" })
    await user.click(within(dialog).getByRole("combobox", { name: "订阅产品" }))

    expect(screen.getByRole("option", { name: "Provider Extra 1" })).toBeInTheDocument()
    expect(screen.getByRole("option", { name: "Provider Extra 2" })).toBeInTheDocument()
    expect(screen.getByRole("option", { name: "OpenAI 接口" })).toBeInTheDocument()
    expect(screen.getByRole("option", { name: "Anthropic 接口" })).toBeInTheDocument()
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
      "请选择",
      "OpenAI 接口",
      "Anthropic 接口",
      "Provider Extra 1",
      "Provider Extra 2",
    ])
    expect(screen.queryByRole("option", { name: "Provider 1" })).not.toBeInTheDocument()
    expect(screen.queryByRole("option", { name: "自定义 OpenAI 兼容接口" })).not.toBeInTheDocument()
  })

  it("opens Anthropic interface configuration with its protocol and auth defaults", async () => {
    const user = userEvent.setup()
    vi.mocked(ownerProviderCatalog).mockResolvedValue([product])
    renderPanel()

    await user.click(await screen.findByRole("button", { name: "添加其他订阅" }))
    const dialog = screen.getByRole("dialog", { name: "添加其他订阅" })
    await user.click(within(dialog).getByRole("combobox", { name: "订阅产品" }))
    await user.click(screen.getByRole("option", { name: "Anthropic 接口" }))
    await user.click(within(dialog).getByRole("button", { name: "继续" }))

    const formDialog = screen.getByRole("dialog", { name: "配置 Anthropic 接口" })
    expect(within(formDialog).getByRole("combobox", { name: "API 协议" })).toHaveTextContent("Anthropic Messages")
    expect(within(formDialog).getByRole("combobox", { name: "认证方式" })).toHaveTextContent("X-API-Key")
  })

  it("opens OpenAI interface configuration with its protocol and auth defaults", async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.click(await screen.findByRole("button", { name: "添加其他订阅" }))
    const dialog = screen.getByRole("dialog", { name: "添加其他订阅" })
    await user.click(within(dialog).getByRole("combobox", { name: "订阅产品" }))
    await user.click(screen.getByRole("option", { name: "OpenAI 接口" }))
    await user.click(within(dialog).getByRole("button", { name: "继续" }))

    const formDialog = screen.getByRole("dialog", { name: "配置 OpenAI 接口" })
    expect(within(formDialog).getByRole("combobox", { name: "API 协议" })).toHaveTextContent("OpenAI Chat Completions")
    expect(within(formDialog).getByRole("combobox", { name: "认证方式" })).toHaveTextContent("Bearer")
  })

  it("verifies one connection and refreshes visible state", async () => {
    const user = userEvent.setup()
    renderPanel()

    const card = within(await screen.findByRole("region", { name: "已配置的远程订阅" })).getByRole("article")
    await user.click(within(card).getByRole("button", { name: "验证" }))

    expect(verifyProviderConnection).toHaveBeenCalledWith("conn-openai", "csrf")
    expect(await screen.findByText("OpenAI Main 验证已完成。")).toBeInTheDocument()
    expect(vi.mocked(ownerProviderConnections).mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it("shows a single non-OpenAI API Key method as a disabled fixed value", async () => {
    const user = userEvent.setup()
    vi.mocked(ownerProviderCatalog).mockResolvedValue([googleProduct])
    renderPanel()

    await user.click(await screen.findByRole("button", { name: "配置 Google" }))

    const dialog = screen.getByRole("dialog", { name: "配置 Google" })
    const methodField = within(dialog).getByRole("group", { name: "连接方式" })
    expect(within(methodField).queryByRole("combobox")).not.toBeInTheDocument()
    expect(within(methodField).getByRole("textbox")).toBeDisabled()
    expect(within(methodField).getByRole("textbox")).toHaveValue("API Key")
  })

  it("turns the connection green as soon as refreshed validation state arrives", async () => {
    const user = userEvent.setup()
    const failedModel = {
      ...model,
      id: "gpt-failed",
      display_name: "GPT Failed",
      verification: { status: "failed" as const, checked_at: "2026-07-30T00:00:00Z", latency_ms: 42, error: "failed" },
    }
    const staleConnection = {
      ...connection,
      verification: { ...connection.verification, status: "failed" as const },
      models: [model, failedModel],
    }
    const refreshedConnection = {
      ...staleConnection,
      verification: { ...connection.verification, status: "passed" as const },
      models: [model, { ...failedModel, verification: { ...failedModel.verification, status: "passed" as const, error: null } }],
    }
    vi.mocked(ownerProviderConnections)
      .mockResolvedValueOnce([staleConnection])
      .mockResolvedValue([refreshedConnection])

    renderPanel()
    const card = within(await screen.findByRole("region", { name: "已配置的远程订阅" })).getByRole("article")
    expect(within(card).getByText("部分可用")).toBeInTheDocument()

    await user.click(within(card).getByRole("button", { name: "验证" }))

    expect(await within(card).findByText("验证通过")).toBeInTheDocument()
    expect(within(card).getByText("共 2 个模型（已启用 2 个 · 验证通过 2 个）")).toBeInTheDocument()
  })

  it("creates a catalog connection through the product-specific form", async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.click(await screen.findByRole("button", { name: "配置 OpenAI" }))
    const dialog = screen.getByRole("dialog", { name: "配置 OpenAI" })
    expect(within(dialog).getByRole("combobox", { name: "连接方式" })).toHaveTextContent("OpenAI API Key（按量计费）")
    await user.click(within(dialog).getByRole("button", { name: "继续" }))
    await user.type(within(dialog).getByLabelText("API 密钥", { selector: "input" }), "secret")
    await user.click(within(dialog).getByRole("button", { name: "保存配置" }))

    await waitFor(() => expect(createProviderConnection).toHaveBeenCalledWith(
      expect.objectContaining({ api_key: "secret", catalog_id: "openai", refresh_models: true }),
      "csrf",
    ))
    expect(vi.mocked(createProviderConnection).mock.calls[0]?.[0]).toHaveProperty("verify", false)
    expect(screen.queryByRole("dialog", { name: "配置 OpenAI" })).not.toBeInTheDocument()
    expect(await screen.findByText("OpenAI Main 已保存。")).toBeInTheDocument()
    expect(vi.mocked(ownerProviderConnections).mock.calls.length).toBeGreaterThanOrEqual(2)
  }, 10_000)

  it("keeps a provider form save failure inside the active dialog", async () => {
    const user = userEvent.setup()
    vi.mocked(createProviderConnection).mockRejectedValueOnce(new ApiError(400, "后端拒绝了订阅配置"))
    renderPanel()

    await user.click(await screen.findByRole("button", { name: "配置 OpenAI" }))
    const dialog = screen.getByRole("dialog", { name: "配置 OpenAI" })
    await user.click(within(dialog).getByRole("button", { name: "继续" }))
    await user.type(within(dialog).getByLabelText("API 密钥", { selector: "input" }), "secret")
    await user.click(within(dialog).getByRole("button", { name: "保存配置" }))

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("后端拒绝了订阅配置")
    expect(screen.getAllByRole("alert")).toHaveLength(1)
  })

  it("keeps the batch validation report inline instead of converting it to a toast", async () => {
    const user = userEvent.setup()
    const staleConnection = {
      ...connection,
      verification: { ...connection.verification, status: "never" as const, checked_at: null, latency_ms: null },
      models: [{ ...model, verification: { ...model.verification, status: "never" as const, checked_at: null, latency_ms: null } }],
    }
    vi.mocked(ownerProviderConnections)
      .mockResolvedValueOnce([staleConnection])
      .mockResolvedValue([connection])
    renderPanel()

    const card = within(await screen.findByRole("region", { name: "已配置的远程订阅" })).getByRole("article")
    expect(within(card).getByText("未验证")).toBeInTheDocument()
    await user.click(await screen.findByRole("button", { name: "批量验证" }))

    expect(await screen.findByRole("status")).toHaveTextContent("批量验证完成：1 项通过，报告 validation-run。")
    expect(within(card).getByText("验证通过")).toBeInTheDocument()
    expect(within(card).getByText("共 1 个模型（已启用 1 个 · 验证通过 1 个）")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("keeps a batch validation failure as an inline alert", async () => {
    const user = userEvent.setup()
    vi.mocked(validateAllProviderModels).mockRejectedValueOnce(new ApiError(502, "批量验证服务不可用"))
    renderPanel()

    await user.click(await screen.findByRole("button", { name: "批量验证" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("批量验证服务不可用")
    expect(screen.queryByText("批量验证完成：1 项通过，报告 validation-run。" )).not.toBeInTheDocument()
  })

  it("forces a full validation from the lifecycle menu", async () => {
    const user = userEvent.setup()
    renderPanel()

    const card = within(await screen.findByRole("region", { name: "已配置的远程订阅" })).getByRole("article")
    await user.click(within(card).getByRole("button", { name: "更多" }))
    await user.click(screen.getByRole("menuitem", { name: "强制全量验证" }))

    expect(verifyProviderConnection).toHaveBeenCalledWith("conn-openai", "csrf", true)
    expect(await screen.findByText("OpenAI Main 已完成强制全量验证。")).toBeInTheDocument()
  })

  it("does not show an all-unverified connection as failed", async () => {
    vi.mocked(ownerProviderConnections).mockResolvedValue([{
      ...connection,
      verification: { status: "never", checked_at: null, latency_ms: null, error: null },
      models: [{ ...model, verification: { status: "never", checked_at: null, latency_ms: null, error: null } }],
    }])
    renderPanel()

    const card = within(await screen.findByRole("region", { name: "已配置的远程订阅" })).getByRole("article")
    expect(card).toHaveClass("provider-card--never")
    expect(within(card).getByText("未验证")).toBeInTheDocument()
    expect(within(card).queryByText("验证失败")).not.toBeInTheDocument()
  })

  it("keeps all-passed models green while showing a stale-validation hint", async () => {
    vi.mocked(ownerProviderConnections).mockResolvedValue([{
      ...connection,
      verification: { ...connection.verification, needs_full_validation: true },
    }])
    renderPanel()

    const card = within(await screen.findByRole("region", { name: "已配置的远程订阅" })).getByRole("article")
    expect(card).toHaveClass("provider-card--passed")
    expect(card).not.toHaveClass("provider-card--partial")
    expect(within(card).getByText("验证通过")).toBeInTheDocument()
    expect(within(card).getByText("需要重新进行全量验证")).toBeInTheDocument()
  })

  it("archives an existing connection from the anchored lifecycle menu", async () => {
    const user = userEvent.setup()
    renderPanel()

    const card = within(await screen.findByRole("region", { name: "已配置的远程订阅" })).getByRole("article")
    await user.click(within(card).getByRole("button", { name: "更多" }))
    const menu = screen.getByRole("menu")
    expect(screen.queryByRole("dialog", { name: "更多操作" })).not.toBeInTheDocument()
    await user.click(within(menu).getByRole("menuitem", { name: "归档" }))

    expect(changeProviderConnectionLifecycle).toHaveBeenCalledWith("conn-openai", "archive", "csrf")
  })

  it("keeps Ollama in its own card and shows only install before it is available", async () => {
    renderPanel()
    const local = await screen.findByRole("region", { name: "本地模型服务" })
    const card = within(local).getByRole("article")

    expect(within(card).getByRole("heading", { name: "Ollama" })).toBeInTheDocument()
    expect(within(card).getByText("0 个可用模型")).toBeInTheDocument()
    expect(within(card).getByRole("button", { name: "安装" })).toBeInTheDocument()
    expect(within(card).queryByRole("button", { name: "模型" })).not.toBeInTheDocument()
    expect(within(card).queryByRole("button", { name: "启动" })).not.toBeInTheDocument()
    expect(within(card).queryByRole("button", { name: "重启" })).not.toBeInTheDocument()
    expect(within(await screen.findByRole("region", { name: "已配置的远程订阅" })).queryByText("Ollama")).not.toBeInTheDocument()
  })

  it("switches the local card from start to restart when Ollama is healthy", async () => {
    const user = userEvent.setup()
    vi.mocked(ownerOllamaStatus).mockResolvedValue(healthyOllama)
    renderPanel()

    const card = within(await screen.findByRole("region", { name: "本地模型服务" })).getByRole("article")
    expect(within(card).getByText("1 个可用模型")).toBeInTheDocument()
    expect(within(card).getByRole("button", { name: "模型" })).toBeInTheDocument()
    expect(within(card).getByRole("button", { name: "重启" })).toBeInTheDocument()
    expect(within(card).queryByRole("button", { name: "启动" })).not.toBeInTheDocument()

    await user.click(within(card).getByRole("button", { name: "重启" }))
    expect(startOllama).toHaveBeenCalledWith("csrf")
  })

  it("opens the recommended Ollama model list and downloads one candidate directly", async () => {
    const user = userEvent.setup()
    vi.mocked(ownerOllamaStatus).mockResolvedValue(healthyOllama)
    renderPanel()

    const card = within(await screen.findByRole("region", { name: "本地模型服务" })).getByRole("article")
    await user.click(within(card).getByRole("button", { name: "模型" }))

    const dialog = screen.getByRole("dialog", { name: "Ollama 模型" })
    expect(within(dialog).getAllByText("qwen2.5:0.5b")).not.toHaveLength(0)
    expect(within(dialog).getByText("qwen3.5:0.8b")).toBeInTheDocument()
    expect(within(dialog).getByText("gemma3:270m")).toBeInTheDocument()
    expect(within(dialog).getByText("已下载")).toBeInTheDocument()
    await user.click(within(dialog).getAllByRole("button", { name: "下载安装" })[0]!)

    expect(pullOllamaModels).toHaveBeenCalledWith(["qwen3.5:0.8b"], "csrf")
  })

  it("relocalizes a stored backend failure without losing the page", async () => {
    vi.mocked(ownerProviderConnections).mockRejectedValue(new ApiError(503, "后端失败"))
    const instance = renderPanel("zh-CN")
    expect(await screen.findByRole("alert")).toHaveTextContent("后端失败")

    await instance.changeLanguage("en-US")
    expect(screen.queryByRole("heading", { name: "Providers and model connections" })).not.toBeInTheDocument()
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to load management data.")
    expect(screen.queryByText("后端失败")).not.toBeInTheDocument()
  })
})

function renderPanel(locale: SupportedLocale = "zh-CN"): ReturnType<typeof createI18n> {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  document.documentElement.lang = locale
  render(<I18nextProvider i18n={instance}><ToastProvider><OwnerProviderPanel csrfToken="csrf" /></ToastProvider></I18nextProvider>)
  return instance
}
