import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

import { ApiError } from "../api/http"
import type { ProviderConnection, ProviderModel, ProviderProduct } from "../api/owner-providers"
import * as providerClient from "../api/owner-providers"
import type { ClientUser } from "../api/session"
import * as sessionClient from "../api/session"
import * as setupClient from "../api/setup"
import type { SetupStatus } from "../api/setup"
import { createI18n } from "../i18n/config"
import { initializeLocale, type SupportedLocale } from "../i18n/locale"
import { SetupPage } from "./SetupPage"

const verification = {
  status: "passed" as const,
  checked_at: "2026-09-04T00:00:00Z",
  latency_ms: 20,
  error: null,
}

function providerModel(id: string): ProviderModel {
  return {
    id,
    display_name: id,
    canonical_model_id: null,
    source: "manual",
    context_window_tokens: null,
    max_output_tokens: null,
    supports_tools: null,
    supports_vision: null,
    supports_reasoning: null,
    hidden: false,
    retired: false,
    available: true,
    verification,
  }
}

function providerProduct(
  brandId: string,
  name: string,
  catalogId = `${brandId}_api`,
): ProviderProduct {
  return {
    catalog_id: catalogId,
    name,
    brand: { brand_id: brandId, name, logo_asset: "" },
    connection_method: "api_key",
    oauth_available: false,
    usage_scope: "remote",
    discovery_strategy: "remote",
    api_mode: "openai_responses",
    api_key_url: null,
  }
}

const apiProduct = providerProduct("openai", "OpenAI API", "openai_api")
const oauthProduct: ProviderProduct = {
  ...apiProduct,
  catalog_id: "chatgpt_oauth",
  name: "ChatGPT subscription",
  connection_method: "oauth",
  oauth_available: true,
  discovery_strategy: "oauth",
}

function providerConnection(models: readonly ProviderModel[] = [providerModel("gpt-4o-mini")]): ProviderConnection {
  return {
    connection_id: "connection-openai",
    catalog_id: apiProduct.catalog_id,
    alias: apiProduct.name,
    api_base: "https://api.openai.com/v1",
    api_mode: apiProduct.api_mode,
    auth_type: "bearer",
    has_api_key: true,
    has_credential: true,
    enabled: true,
    archived: false,
    usage_scope: apiProduct.usage_scope,
    verification,
    models: [...models],
    model_counts: {
      total: models.length,
      enabled: models.length,
      in_use: models.length,
      available: models.length,
      degraded: 0,
      pending: 0,
      unavailable: 0,
    },
    model_refresh: null,
  }
}

const ownerUser: ClientUser = {
  user_id: 1,
  account_id: "owner",
  display_name: "Owner",
  role: "owner",
  theme_key: "warm-paper",
  csrf_token: "session-csrf",
}

function statusFor(currentStep: 1 | 2 | 3, overrides: Partial<SetupStatus> = {}): SetupStatus {
  const baseDraft: SetupStatus["draft"] = {
    owner_account_id: currentStep > 1 ? "owner" : null,
    display_name: currentStep > 1 ? "Owner" : null,
    password_configured: currentStep > 1,
    use_local_ollama: currentStep > 2 ? false : null,
    ollama_installed: false,
    model_id: null,
    bed_count: 12,
    owner_configured: currentStep > 1,
    offline_configured: currentStep > 2,
    nest_configured: currentStep > 2,
    locked_at: null,
    remote_configured: currentStep > 2,
    remote_skipped: false,
    remote_connection_id: currentStep > 2 ? "connection-openai" : null,
  }
  const draft = { ...baseDraft, ...(overrides.draft ?? {}) }
  const complete = overrides.complete ?? false
  const install = overrides.install ?? {
    phase: "model_validation" as const,
    action_key: "idle",
    state: "idle" as const,
    progress: 0,
    error_key: null,
  }
  const configured = [
    draft.owner_configured,
    draft.remote_configured || draft.remote_skipped || draft.offline_configured,
    complete,
  ]
  const steps = configured.map((value, index) => ({
    name: ["创建账号", "配置大模型订阅", "完成"][index] ?? "",
    number: index + 1,
    status: value ? "completed" as const : index + 1 === currentStep ? "current" as const : "pending" as const,
    retry_action: index === 2 && install.state !== "idle" && install.state !== "completed" ? "retry_install" : null,
  }))
  return {
    ...overrides,
    need_setup: overrides.need_setup ?? !complete,
    complete,
    current_step: overrides.current_step ?? currentStep,
    locked: overrides.locked ?? false,
    csrf_token: overrides.csrf_token ?? "setup-csrf",
    draft,
    steps,
    last_error: overrides.last_error ?? null,
    install,
  }
}

function renderSetup(
  status: SetupStatus,
  {
    locale = "en-US",
    products = [apiProduct, oauthProduct],
    connections = [],
  }: {
    readonly locale?: SupportedLocale
    readonly products?: readonly ProviderProduct[]
    readonly connections?: readonly ProviderConnection[]
  } = {},
): void {
  vi.spyOn(setupClient, "setupStatus").mockResolvedValue(status)
  vi.spyOn(sessionClient, "currentUser").mockResolvedValue(ownerUser)
  vi.spyOn(providerClient, "ownerProviderCatalog").mockResolvedValue(products)
  vi.spyOn(providerClient, "ownerProviderConnections").mockResolvedValue(connections)
  vi.spyOn(providerClient, "ensureProviderModelAvailability").mockResolvedValue({
    status: "available",
    reason_code: null,
  })
  const instance = createI18n()
  initializeLocale(instance, {
    browserLanguages: [locale],
    documentElement: document.documentElement,
    storage: localStorage,
  })
  render(
    <I18nextProvider i18n={instance}>
      <SetupPage />
    </I18nextProvider>,
  )
}

describe("localized setup wizard", () => {
  beforeAll(() => {
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("opens with the welcome animation and then enters the three-step setup flow", async () => {
    const user = userEvent.setup()
    renderSetup(statusFor(1))

    expect(await screen.findByRole("button", { name: "Begin" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Begin" }))
    expect(await screen.findByRole("heading", { level: 1, name: "Create the Owner account" })).toBeInTheDocument()
    expect(screen.getAllByRole("listitem")).toHaveLength(3)
    for (const label of ["Create account", "Configure model subscription", "Finish"]) expect(screen.getByText(label)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Begin" })).not.toBeInTheDocument()
    expect(screen.queryByText(/Ollama|Review|Bed count|Local offline/i)).not.toBeInTheDocument()
  })

  it("writes the Owner draft and establishes the Owner session before step two", async () => {
    const user = userEvent.setup()
    const save = vi.spyOn(setupClient, "setupSaveOwnerDraft").mockResolvedValue(statusFor(2))
    renderSetup(statusFor(1))

    await user.click(await screen.findByRole("button", { name: "Begin" }))
    await user.type(await screen.findByRole("textbox", { name: "Owner account" }), "owner")
    await user.type(screen.getByRole("textbox", { name: "Display name" }), "Owner")
    await user.type(within(screen.getByRole("group", { name: "Password" })).getByLabelText("Password"), "owner-secret")
    await user.type(within(screen.getByRole("group", { name: "Confirm password" })).getByLabelText("Confirm password"), "owner-secret")
    await user.click(screen.getByRole("button", { name: "Save and continue" }))

    await waitFor(() => expect(save).toHaveBeenCalledWith("owner", "Owner", "owner-secret", "owner-secret", "setup-csrf"))
    expect(sessionClient.currentUser).toHaveBeenCalled()
    expect(providerClient.ownerProviderCatalog).toHaveBeenCalled()
    expect(await screen.findByRole("heading", { level: 1, name: "Configure model subscription" })).toBeInTheDocument()
  }, 10_000)

  it("uses only API-key products and follows the subscription Provider order with Custom last", async () => {
    const products = [
      providerProduct("custom", "Custom", "custom_openai"),
      providerProduct("xai", "xAI"),
      providerProduct("deepseek", "DeepSeek"),
      providerProduct("openai", "OpenAI"),
      providerProduct("anthropic", "Anthropic"),
      providerProduct("mistral", "Mistral AI"),
      providerProduct("google", "Google"),
      providerProduct("alibaba", "Alibaba Cloud"),
      providerProduct("zhipu", "Zhipu AI (GLM)"),
      providerProduct("moonshot", "Kimi (Moonshot AI)"),
      providerProduct("minimax", "MiniMax"),
      providerProduct("volcengine", "火山引擎"),
      providerProduct("openrouter", "OpenRouter"),
      providerProduct("siliconflow", "SiliconFlow"),
      providerProduct("groq", "Groq"),
      oauthProduct,
    ]
    const user = userEvent.setup()
    renderSetup(statusFor(2), { products })

    const provider = await screen.findByRole("combobox", { name: "Provider" })
    await user.click(provider)
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Google",
      "OpenAI",
      "Anthropic",
      "DeepSeek",
      "Alibaba Cloud",
      "Zhipu AI (GLM)",
      "Kimi (Moonshot AI)",
      "MiniMax",
      "火山引擎",
      "xAI",
      "OpenRouter",
      "SiliconFlow",
      "Groq",
      "Custom interface",
    ])
    expect(screen.queryByText("Mistral AI")).not.toBeInTheDocument()
    expect(screen.queryByText("ChatGPT subscription")).not.toBeInTheDocument()

    await user.click(screen.getByRole("option", { name: "Custom interface" }))
    const connectionMethod = await screen.findByRole("combobox", { name: "Connection method" })
    await user.click(connectionMethod)
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual(["OpenAI interface", "Anthropic interface"])
  })

  it("discovers models automatically after the API key is entered", async () => {
    const user = userEvent.setup()
    const created = providerConnection([providerModel("gpt-4o-mini"), providerModel("gpt-4.1-mini")])
    const create = vi.spyOn(providerClient, "createProviderConnection").mockResolvedValue(created)
    renderSetup(statusFor(2))

    const key = await screen.findByRole("textbox", { name: "API Key" })
    await user.type(key, "sk-test-key")
    await user.tab()

    await waitFor(() => expect(create).toHaveBeenCalledWith({
      catalog_id: "openai_api",
      api_key: "sk-test-key",
      models: [],
      refresh_models: true,
      defer_validation: true,
    }, "session-csrf", { timeout: 2_000 }))
    expect(await screen.findByRole("textbox", { name: "Models" })).toHaveValue("gpt-4o-mini, gpt-4.1-mini")
  })

  it("shows a saved API key as a mask without the old leave-blank hint", async () => {
    renderSetup(statusFor(2), { connections: [providerConnection()] })

    const key = await screen.findByRole("textbox", { name: "API Key" })
    expect(key).toHaveValue("••••••••••••")
    expect(key).toHaveAttribute("type", "text")
    expect(key).toHaveAttribute("autocomplete", "off")
    expect(key).toHaveAttribute("name", "api-key")
    expect(key).toHaveAttribute("data-form-type", "other")
    expect(screen.queryByText("The API key is already saved; leave blank to continue.")).not.toBeInTheDocument()
  })

  it("shows a two-second discovery failure and allows manual model entry", async () => {
    const user = userEvent.setup()
    const created = providerConnection([providerModel("manual-model")])
    const create = vi.spyOn(providerClient, "createProviderConnection")
      .mockRejectedValueOnce(new ApiError(504, "model discovery timed out"))
      .mockResolvedValue(created)
    const setupSave = vi.spyOn(setupClient, "setupSaveRemoteDraft").mockResolvedValue(statusFor(3))
    const install = vi.spyOn(setupClient, "setupInstall").mockResolvedValue(statusFor(3, {
      locked: true,
      install: { phase: "model_validation", action_key: "model.validation.start", state: "running", progress: 20, error_key: null },
    }))
    renderSetup(statusFor(2))

    const key = await screen.findByRole("textbox", { name: "API Key" })
    await user.type(key, "sk-test-key")
    await user.tab()
    expect(await screen.findByText("Model fetch failed. Enter model IDs manually.")).toBeInTheDocument()

    const models = screen.getByRole("textbox", { name: "Models" })
    await user.type(models, "manual-model")
    await user.click(screen.getByRole("button", { name: "Validate and continue" }))

    await waitFor(() => expect(create).toHaveBeenLastCalledWith({
      catalog_id: "openai_api",
      api_key: "sk-test-key",
      models: [{ id: "manual-model" }],
      refresh_models: false,
      defer_validation: true,
    }, "session-csrf"))
    await waitFor(() => expect(setupSave).toHaveBeenCalledWith(true, "connection-openai", "setup-csrf"))
    expect(install).toHaveBeenCalledWith("setup-csrf")
  }, 10_000)

  it("accepts comma or newline separated model IDs and trims duplicate spacing", async () => {
    const user = userEvent.setup()
    renderSetup(statusFor(2), { connections: [providerConnection()] })

    const models = await screen.findByRole("textbox", { name: "Models" })
    await user.clear(models)
    await user.type(models, " gpt-a,  gpt-b\n gpt-a ")
    await user.tab()

    expect(models).toHaveValue("gpt-a, gpt-b")
  })

  it("saves the discovered models and performs one Step 2 smoke check", async () => {
    const user = userEvent.setup()
    const created = providerConnection([providerModel("gpt-5.4"), providerModel("gpt-4o-mini")])
    vi.spyOn(providerClient, "createProviderConnection").mockResolvedValue(created)
    const update = vi.spyOn(providerClient, "updateProviderConnection").mockResolvedValue(created)
    const setupSave = vi.spyOn(setupClient, "setupSaveRemoteDraft").mockResolvedValue(statusFor(3))
    vi.spyOn(setupClient, "setupInstall").mockResolvedValue(statusFor(3, {
      locked: true,
      install: { phase: "model_validation", action_key: "model.validation.start", state: "running", progress: 20, error_key: null },
    }))
    renderSetup(statusFor(2))

    const key = await screen.findByRole("textbox", { name: "API Key" })
    await user.type(key, "sk-test-key")
    await user.tab()
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Models" })).toHaveValue("gpt-5.4, gpt-4o-mini"))
    await user.click(screen.getByRole("button", { name: "Validate and continue" }))

    await waitFor(() => expect(update).toHaveBeenCalledWith("connection-openai", {
      api_key: "sk-test-key",
      models: [{ id: "gpt-5.4" }, { id: "gpt-4o-mini" }],
      refresh_models: false,
      defer_validation: true,
    }, "session-csrf"))
    await waitFor(() => expect(providerClient.ensureProviderModelAvailability).toHaveBeenCalledWith(
      "connection-openai",
      "gpt-4o-mini",
      "session-csrf",
      { timeout: 25_000 },
    ))
    await waitFor(() => expect(setupSave).toHaveBeenCalledWith(true, "connection-openai", "setup-csrf"))
  })

  it("runs one lightweight model check before entering step three", async () => {
    const user = userEvent.setup()
    const existing = providerConnection()
    const updated = providerConnection([providerModel("gpt-4o-mini"), providerModel("gpt-4.1-mini")])
    const update = vi.spyOn(providerClient, "updateProviderConnection").mockResolvedValue(updated)
    const setupSave = vi.spyOn(setupClient, "setupSaveRemoteDraft").mockResolvedValue(statusFor(3))
    const install = vi.spyOn(setupClient, "setupInstall").mockResolvedValue(statusFor(3, {
      locked: true,
      install: { phase: "model_validation", action_key: "model.validation.start", state: "running", progress: 20, error_key: null },
    }))
    renderSetup(statusFor(2), { connections: [existing] })

    const models = await screen.findByRole("textbox", { name: "Models" })
    await user.clear(models)
    await user.type(models, "gpt-4o-mini, gpt-4.1-mini")
    await user.click(screen.getByRole("button", { name: "Validate and continue" }))

    await waitFor(() => expect(update).toHaveBeenCalledWith("connection-openai", {
      models: [{ id: "gpt-4o-mini" }, { id: "gpt-4.1-mini" }],
      refresh_models: false,
      defer_validation: true,
    }, "session-csrf"))
    await waitFor(() => expect(providerClient.ensureProviderModelAvailability).toHaveBeenCalledWith(
      "connection-openai",
      "gpt-4o-mini",
      "session-csrf",
      { timeout: 25_000 },
    ))
    await waitFor(() => expect(setupSave).toHaveBeenCalledWith(true, "connection-openai", "setup-csrf"))
    expect(install).toHaveBeenCalledWith("setup-csrf")
  })

  it("keeps the Step 2 action label unchanged while the check is running", async () => {
    const user = userEvent.setup()
    const existing = providerConnection()
    const updated = providerConnection()
    let resolveAvailability: ((value: { status: "available"; reason_code: null }) => void) | undefined
    const availability = new Promise<{ status: "available"; reason_code: null }>((resolve) => {
      resolveAvailability = resolve
    })
    vi.spyOn(providerClient, "updateProviderConnection").mockResolvedValue(updated)
    vi.spyOn(setupClient, "setupSaveRemoteDraft").mockResolvedValue(statusFor(3))
    vi.spyOn(setupClient, "setupInstall").mockResolvedValue(statusFor(3, { locked: true }))
    renderSetup(statusFor(2), { connections: [existing] })
    vi.mocked(providerClient.ensureProviderModelAvailability).mockResolvedValue(
      availability as unknown as Awaited<ReturnType<typeof providerClient.ensureProviderModelAvailability>>,
    )

    const action = await screen.findByRole("button", { name: "Validate and continue" })
    await user.click(action)

    expect(screen.getByRole("button", { name: "Validate and continue" })).toBeDisabled()
    expect(screen.queryByRole("button", { name: /Saving|Validating/ })).not.toBeInTheDocument()
    resolveAvailability?.({ status: "available", reason_code: null })
  })

  it("keeps step two open when the lightweight model check fails", async () => {
    const user = userEvent.setup()
    const existing = providerConnection()
    const updated = providerConnection([providerModel("gpt-4o-mini")])
    vi.spyOn(providerClient, "updateProviderConnection").mockResolvedValue(updated)
    const setupSave = vi.spyOn(setupClient, "setupSaveRemoteDraft")
    renderSetup(statusFor(2), { connections: [existing] })
    vi.mocked(providerClient.ensureProviderModelAvailability).mockResolvedValue({
      status: "unavailable",
      reason_code: "invalid_credential",
    })

    await user.click(await screen.findByRole("button", { name: "Validate and continue" }))

    await waitFor(() => expect(providerClient.ensureProviderModelAvailability).toHaveBeenCalled())
    expect(setupSave).not.toHaveBeenCalled()
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The subscription or model validation failed. Check the API key and model IDs.",
    )
    expect(screen.getByRole("heading", { level: 1, name: "Configure model subscription" })).toBeInTheDocument()
  })

  it("keeps a failed subscription save on step two for correction", async () => {
    const user = userEvent.setup()
    const existing = providerConnection()
    const update = vi.spyOn(providerClient, "updateProviderConnection").mockRejectedValue(new ApiError(422, "API Key 无效或已过期"))
    const save = vi.spyOn(setupClient, "setupSaveRemoteDraft")
    renderSetup(statusFor(2), { connections: [existing] })

    await user.click(await screen.findByRole("button", { name: "Validate and continue" }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to save setup.")
    expect(save).not.toHaveBeenCalled()
    expect(screen.getByRole("textbox", { name: "Models" })).toBeInTheDocument()
  })

  it("persists Skip and starts the third-step preparation without pretending Food is ready", async () => {
    const user = userEvent.setup()
    const skippedDraft = { ...statusFor(3).draft, remote_configured: false, remote_skipped: true, remote_connection_id: null }
    const save = vi.spyOn(setupClient, "setupSaveRemoteDraft").mockResolvedValue(statusFor(3, { draft: skippedDraft }))
    const install = vi.spyOn(setupClient, "setupInstall").mockResolvedValue(statusFor(3, {
      locked: true,
      draft: skippedDraft,
      install: { phase: "model_validation", action_key: "model.validation.skipped", state: "running", progress: 20, error_key: null },
    }))
    renderSetup(statusFor(2))

    await user.click(await screen.findByRole("button", { name: "Set up later" }))

    await waitFor(() => expect(save).toHaveBeenCalledWith(false, null, "setup-csrf"))
    expect(install).toHaveBeenCalledWith("setup-csrf")
  })

  it("shows a retry when starting the persisted third step fails", async () => {
    const user = userEvent.setup()
    const skippedDraft = { ...statusFor(3).draft, remote_configured: false, remote_skipped: true, remote_connection_id: null }
    const saved = statusFor(3, { draft: skippedDraft })
    vi.spyOn(setupClient, "setupSaveRemoteDraft").mockResolvedValue(saved)
    const install = vi.spyOn(setupClient, "setupInstall").mockRejectedValue(new ApiError(503, "安装任务不可用"))
    renderSetup(statusFor(2))
    const setupStatus = vi.mocked(setupClient.setupStatus)
    await screen.findByRole("heading", { level: 1, name: "Configure model subscription" })
    setupStatus.mockReset().mockResolvedValue(saved)

    await user.click(await screen.findByRole("button", { name: "Set up later" }))
    await waitFor(() => expect(install).toHaveBeenCalledWith("setup-csrf"))
    expect(await screen.findByRole("heading", { level: 1, name: "Preparation failed" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Go to Manage" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument()
  })

  it("shows persisted third-step progress and sends a configured setup to adoption", async () => {
    const redirects = { assign: vi.fn() }
    vi.stubGlobal("location", { assign: redirects.assign })
    renderSetup(statusFor(3, {
      complete: true,
      locked: true,
      install: { phase: "runtime", action_key: "runtime.ready.complete", state: "completed", progress: 100, error_key: null },
    }))

    expect(await screen.findByRole("heading", { level: 1, name: "Preparation complete" })).toBeInTheDocument()
    expect(screen.getByRole("progressbar", { name: "Finishing setup" })).toHaveAttribute("aria-valuenow", "100")
    expect(screen.getByText("[100%] Preparation complete")).toBeInTheDocument()
    expect(screen.queryByRole("list", { name: "Preparation progress" })).not.toBeInTheDocument()
    expect(screen.queryByText("Step 3 of 3")).not.toBeInTheDocument()
    expect(screen.queryByText(/Review|Bed count|confirmation|Ollama/i)).not.toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole("button", { name: "Start adoption" }))
    expect(redirects.assign).toHaveBeenCalledWith("/")
  })

  it("routes a completed skipped setup to Manage and keeps a running setup actionless", async () => {
    const redirects = { assign: vi.fn() }
    vi.stubGlobal("location", { assign: redirects.assign })
    const skippedDraft = { ...statusFor(3).draft, remote_configured: false, remote_skipped: true, remote_connection_id: null }
    renderSetup(statusFor(3, {
      complete: true,
      locked: true,
      draft: skippedDraft,
      install: { phase: "runtime", action_key: "runtime.ready.complete", state: "completed", progress: 100, error_key: null },
    }))

    await userEvent.setup().click(await screen.findByRole("button", { name: "Go to Manage" }))
    expect(redirects.assign).toHaveBeenCalledWith("/")

    cleanup()
    vi.unstubAllGlobals()
    renderSetup(statusFor(3, {
      locked: true,
      install: { phase: "runtime", action_key: "runtime.ready.start", state: "running", progress: 90, error_key: null },
    }))
    expect(await screen.findByRole("heading", { level: 1, name: "Preparing the nest" })).toBeInTheDocument()
    expect(screen.getByRole("progressbar", { name: "Finishing setup" })).toHaveAttribute("aria-valuenow", "90")
    expect(screen.getByText("[90%] Waiting for the nest Runtime…")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Start adoption" })).not.toBeInTheDocument()
  })

  it("shows a third-step failure with Manage and Retry but no back navigation", async () => {
    const retry = vi.spyOn(setupClient, "setupInstall").mockResolvedValue(statusFor(3, { locked: true }))
    renderSetup(statusFor(3, {
      locked: true,
      last_error: "没有可用的远程模型",
      install: { phase: "model_validation", action_key: "model.validation.start", state: "failed", progress: 20, error_key: "setup.install.failed" },
    }))

    expect(await screen.findByRole("heading", { level: 1, name: "Preparation failed" })).toBeInTheDocument()
    expect(screen.getByRole("alert")).toHaveTextContent("没有可用的远程模型")
    expect(screen.getByRole("button", { name: "Go to Manage" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Prepare Food/ })).not.toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }))
    await waitFor(() => expect(retry).toHaveBeenCalledWith("setup-csrf"))
  })

  it("keeps the Owner fields as compact horizontal rows", async () => {
    const user = userEvent.setup()
    renderSetup(statusFor(1))
    await user.click(await screen.findByRole("button", { name: "Begin" }))
    const form = await screen.findByRole("textbox", { name: "Owner account" })
    expect(form.closest("form")).toHaveClass("setup-form--owner")
    for (const label of ["Owner account", "Display name", "Password", "Confirm password"]) {
      const field = screen.getByRole("group", { name: label })
      expect(within(field).getByLabelText(label).closest('[data-field-row="true"]')).toBeInTheDocument()
    }
  })

  it("retries an expired Setup CSRF lease for a real owner draft write", async () => {
    const user = userEvent.setup()
    const initial = statusFor(1)
    const refreshed = statusFor(1, { csrf_token: "fresh-setup-csrf" })
    const save = vi.spyOn(setupClient, "setupSaveOwnerDraft")
      .mockRejectedValueOnce(new ApiError(403, "缺少 Setup CSRF token", [], "csrf_rejected"))
      .mockResolvedValue(statusFor(2))
    renderSetup(initial)
    const setupStatus = vi.mocked(setupClient.setupStatus)
    setupStatus.mockReset().mockResolvedValueOnce(initial).mockResolvedValueOnce(refreshed).mockResolvedValue(initial)
    await user.click(await screen.findByRole("button", { name: "Begin" }))
    await user.type(await screen.findByRole("textbox", { name: "Owner account" }), "owner")
    await user.type(screen.getByRole("textbox", { name: "Display name" }), "Owner")
    await user.type(within(screen.getByRole("group", { name: "Password" })).getByLabelText("Password"), "owner-secret")
    await user.type(within(screen.getByRole("group", { name: "Confirm password" })).getByLabelText("Confirm password"), "owner-secret")
    await user.click(screen.getByRole("button", { name: "Save and continue" }))

    await waitFor(() => expect(save).toHaveBeenCalledTimes(2))
    expect(save.mock.calls[0]?.[4]).toBe("setup-csrf")
    expect(save.mock.calls[1]?.[4]).toBe("fresh-setup-csrf")
  })
})
