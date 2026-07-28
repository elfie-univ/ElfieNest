import { fireEvent, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  createProvider,
  benchmarkProviderModels,
  ownerModelMatrix,
  ownerProviders,
  verifyProvidersBatch,
  type ModelMatrix,
  type ProviderView,
} from "../api/owner-providers"
import { OwnerProviderPanel } from "./OwnerProviderPanel"

vi.mock("../api/owner-providers", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-providers")>()
  return {
    ...original,
    benchmarkProviderModels: vi.fn(),
    createProvider: vi.fn(),
    deleteProvider: vi.fn(),
    ownerModelMatrix: vi.fn(),
    ownerProviders: vi.fn(),
    updateProvider: vi.fn(),
    verifyProvider: vi.fn(),
    verifyProvidersBatch: vi.fn(),
  }
})

const baseProvider = {
  provider_id: "ollama",
  name: "Ollama",
  display_name: "",
  api_base: "http://localhost:11434",
  api_mode: "ollama",
  auth_type: "none",
  test_model: "",
  configured: true,
  configuration_status: "configured",
  verification: { status: "passed", checked_at: "2026-07-26T00:00:00Z", latency_ms: 12, error: null },
  has_api_key: false,
  models: [{ id: "qwen3:4b", display_name: "Qwen 3 4B", source: "discovered" }],
  model_refresh: {},
  capabilities: { connection_method: "local", oauth_available: false, oauth_unavailable: false, model_discovery: true },
} satisfies ProviderView

const openai = {
  ...baseProvider,
  provider_id: "openai",
  name: "OpenAI",
  api_base: "https://api.openai.com/v1",
  api_mode: "chat_completions",
  auth_type: "bearer",
  verification: { status: "never", checked_at: null, latency_ms: null, error: null },
  has_api_key: true,
  models: [{ id: "gpt-test", display_name: "GPT Test", source: "manual" }],
  capabilities: { connection_method: "api_key", oauth_available: false, oauth_unavailable: false, model_discovery: true },
} satisfies ProviderView

const anthropic = {
  ...openai,
  provider_id: "anthropic",
  name: "Anthropic",
  api_base: "https://api.anthropic.com/v1",
  auth_type: "x-api-key",
  configured: false,
  configuration_status: "unconfigured",
  has_api_key: false,
  models: [],
} satisfies ProviderView

const modelMatrix = {
  providers: [
    { provider_id: "ollama", name: "Ollama", verification: { status: "passed", checked_at: "2026-07-26T00:00:00Z", latency_ms: 12, error: null } },
    { provider_id: "openai", name: "OpenAI", verification: { status: "never", checked_at: null, latency_ms: null, error: null } },
  ],
  models: [{
    model_id: "qwen3:4b",
    display_name: "Qwen 3 4B",
    capabilities: ["text"],
    providers: [
      { provider_id: "ollama", available: true, verification_status: "passed", benchmark_status: "passed", latency_ms: 12, latency_class: "fast", price_estimate: null },
      { provider_id: "openai", available: false, verification_status: "never", benchmark_status: null, latency_ms: null, latency_class: null, price_estimate: null },
    ],
  }],
} satisfies ModelMatrix

describe("OwnerProviderPanel", () => {
  beforeEach(() => {
    vi.mocked(ownerProviders).mockResolvedValue([anthropic, openai, baseProvider])
    vi.mocked(verifyProvidersBatch).mockResolvedValue({ results: [] })
    vi.mocked(ownerModelMatrix).mockResolvedValue(modelMatrix)
    vi.mocked(benchmarkProviderModels).mockResolvedValue({ results: [] })
  })

  it("separates configured subscriptions from new configuration and constrains actions", async () => {
    render(<OwnerProviderPanel csrfToken="csrf" />)

    const configured = await screen.findByRole("region", { name: "已配置的订阅" })
    const available = screen.getByRole("region", { name: "配置新的订阅" })
    const configuredCards = within(configured).getAllByRole("article")
    const primaryConfiguredCard = configuredCards[0]
    expect(primaryConfiguredCard).toBeDefined()
    if (primaryConfiguredCard === undefined) throw new Error("Expected at least one configured provider card")
    expect(within(primaryConfiguredCard).getByRole("heading", { name: "Ollama" })).toBeInTheDocument()
    expect(within(configured).getAllByText("已配置")).toHaveLength(2)
    expect(within(configured).getByText("未验证")).toBeInTheDocument()
    expect(within(configured).getByRole("button", { name: "删除 Ollama" })).toBeDisabled()

    const anthropicCard = within(available).getByRole("article")
    expect(within(anthropicCard).getByRole("button", { name: "配置 Anthropic" })).toBeInTheDocument()
    expect(within(anthropicCard).queryByRole("button", { name: /验证/ })).not.toBeInTheDocument()
    expect(within(anthropicCard).queryByRole("button", { name: /删除/ })).not.toBeInTheDocument()
  })

  it("uses a filled support-model action and returns focus after keyboard close", async () => {
    const user = userEvent.setup()
    render(<OwnerProviderPanel csrfToken="csrf" />)

    const supportModels = await screen.findByRole("button", { name: "查看支持模型" })
    expect(supportModels).toBeEnabled()

    await user.click(supportModels)
    expect(await screen.findByRole("dialog", { name: "支持模型与测速" })).toBeInTheDocument()
    expect(await screen.findByRole("columnheader", { name: "Ollama" })).toBeInTheDocument()

    await user.keyboard("{Escape}")
    expect(screen.queryByRole("dialog", { name: "支持模型与测速" })).not.toBeInTheDocument()
    expect(supportModels).toHaveFocus()
  })

  it("uses a provider-specific vertical form with model rows instead of pipe text", async () => {
    const user = userEvent.setup()
    render(<OwnerProviderPanel csrfToken="csrf" />)
    const available = await screen.findByRole("region", { name: "配置新的订阅" })
    await user.click(within(available).getByRole("button", { name: "配置 Anthropic" }))

    const dialog = screen.getByRole("dialog", { name: "配置 Anthropic" })
    expect(within(dialog).getByText("anthropic")).toBeInTheDocument()
    expect(within(dialog).getByLabelText("API 密钥", { selector: "input" })).toHaveAttribute("type", "password")
    expect(within(dialog).getByRole("button", { name: "添加模型" })).toBeInTheDocument()
    expect(within(dialog).queryByPlaceholderText(/\|/)).not.toBeInTheDocument()
    expect(within(dialog).queryByRole("textbox", { name: "供应商 ID" })).not.toBeInTheDocument()
  })

  it("creates a custom provider from the add card", async () => {
    const user = userEvent.setup()
    vi.mocked(createProvider).mockResolvedValue({ ...openai, provider_id: "home_gateway", name: "家庭网关" })
    render(<OwnerProviderPanel csrfToken="csrf" />)
    await screen.findByRole("region", { name: "配置新的订阅" })

    await user.click(screen.getByRole("button", { name: "添加自定义供应商" }))
    const dialog = screen.getByRole("dialog", { name: "添加自定义供应商" })
    fireEvent.change(within(dialog).getByRole("textbox", { name: "供应商 ID" }), { target: { value: "home_gateway" } })
    fireEvent.change(within(dialog).getByRole("textbox", { name: "显示名称" }), { target: { value: "家庭网关" } })
    fireEvent.change(within(dialog).getByRole("textbox", { name: "API Base URL" }), { target: { value: "https://gateway.example/v1" } })
    fireEvent.change(within(dialog).getByLabelText("API 密钥", { selector: "input" }), { target: { value: "local-key" } })
    await user.click(within(dialog).getByRole("button", { name: "添加供应商" }))

    expect(createProvider).toHaveBeenCalledWith(expect.objectContaining({
      provider_id: "home_gateway",
      api_base: "https://gateway.example/v1",
      api_key: "local-key",
    }), "csrf")
  })
})
