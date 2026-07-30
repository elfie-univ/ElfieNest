import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

import * as client from "../api/client"
import { ApiError, type SetupStatus } from "../api/client"
import { createI18n } from "../i18n/config"
import { initializeLocale, type SupportedLocale } from "../i18n/locale"
import { SetupPage } from "./SetupPage"

function statusForStep(currentStep: number, task?: SetupStatus["task"]): SetupStatus {
  return {
    complete: false,
    current_step: currentStep,
    need_setup: true,
    last_error: "后端 last_error 不能直接展示",
    task,
    steps: [
      { name: "后端账号步骤", number: 1, status: currentStep > 1 ? "completed" : "current" },
      { name: "后端 Ollama 步骤", number: 2, status: currentStep === 2 ? "current" : currentStep > 2 ? "completed" : "pending" },
      { name: "后端床位步骤", number: 3, status: currentStep === 3 ? "current" : currentStep > 3 ? "completed" : "pending" },
      { name: "后端模型步骤", number: 4, status: currentStep === 4 ? "current" : currentStep > 4 ? "completed" : "pending" },
      { name: "后端完成步骤", number: 5, status: currentStep === 5 ? "current" : "pending" },
    ],
  }
}

function renderSetup(locale: SupportedLocale, status: SetupStatus): void {
  vi.spyOn(client, "setupStatus").mockResolvedValue(status)
  vi.spyOn(client, "currentUser").mockResolvedValue({
    account_id: "owner",
    csrf_token: "csrf-token",
    role: "owner",
    theme_key: "warm-paper",
    username: "owner",
  })
  vi.spyOn(client, "setupModelRecommendation").mockResolvedValue({
    memory_gb: 8,
    recommended_model: "ollama/qwen2.5:0.5b",
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
  })

  it("renders all five English steps from frontend resources and ignores backend step names", async () => {
    // Given: setup progress includes backend natural-language step names.
    renderSetup("en-US", statusForStep(4))

    // When: the model step is displayed.
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "Choose a model and food.",
    )

    // Then: every side-rail step label comes from the English resource bundle.
    for (const label of [
      "Create owner account",
      "Offline fallback (optional)",
      "Nest beds",
      "Model and food",
      "Finish setup",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    expect(screen.queryByText(/后端/)).not.toBeInTheDocument()
  })

  it("keeps owner form state and the URL when switching languages", async () => {
    // Given: a partially filled Chinese owner form.
    const user = userEvent.setup()
    window.history.replaceState({ source: "setup" }, "", "/setup")
    const initialUrl = window.location.href
    renderSetup("zh-CN", statusForStep(1))
    fireEvent.change(await screen.findByLabelText("管理员账号"), { target: { value: "owner" } })
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "secret-pass" } })

    // When: the shared language switcher changes the live setup page to English.
    await user.click(screen.getByRole("combobox", { name: "语言" }))
    await user.click(screen.getByRole("option", { name: "English" }))

    // Then: localized labels change without losing live form state or navigation.
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Set up the home first.")
    expect(screen.getByLabelText("Owner account")).toHaveValue("owner")
    expect(screen.getByLabelText("Password")).toHaveValue("secret-pass")
    expect(window.location.href).toBe(initialUrl)
  })

  it("keeps the language control in the setup frame instead of the active step card", async () => {
    // Given: the wizard is on a later step where owner-account fields are no longer visible.
    renderSetup("zh-CN", statusForStep(4))

    // When: the persistent setup frame is inspected.
    const localeControl = await screen.findByRole("region", { name: "语言" })

    // Then: every step retains one globe language control outside the changing step card.
    expect(localeControl).toContainElement(screen.getByRole("combobox", { name: "语言" }))
    expect(localeControl.closest(".setup-card")).toBeNull()
  })

  it("shows localized running progress without backend task detail", async () => {
    // Given: setup refresh reports a running Ollama task with backend detail fields.
    renderSetup("en-US", statusForStep(2, {
      error: "后端 task.error 不能直接展示",
      key: "install_ollama",
      progress: 37,
      state: "running",
      step: 2,
    }))

    // When: the optional Ollama step renders.
    expect(await screen.findByText("Installing Ollama · 37%")).toBeInTheDocument()

    // Then: only localized progress guidance is visible.
    expect(screen.getByText("Keep this page open; a refresh will show the latest progress.")).toBeInTheDocument()
    expect(screen.queryByText(/后端/)).not.toBeInTheDocument()
  })

  it("shows localized model download progress without backend task detail", async () => {
    renderSetup("en-US", statusForStep(4, {
      error: "后端模型下载失败详情",
      key: "pull_model",
      progress: 64,
      state: "running",
      step: 4,
    }))

    expect(await screen.findByText("Downloading and verifying model · 64%")).toBeInTheDocument()
    expect(screen.queryByText("后端模型下载失败详情")).not.toBeInTheDocument()
  })

  it("falls back to localized actions when a task state is not running", async () => {
    // Given: backend reports an unknown non-running task state.
    renderSetup("en-US", statusForStep(2, {
      error: "后端失败详情",
      key: "install_ollama",
      progress: 41,
      state: "failed",
      step: 2,
    }))

    // When: the page renders the optional Ollama step.
    expect(await screen.findByRole("button", { name: "Bind existing Ollama" })).toBeInTheDocument()

    // Then: backend task detail is not exposed.
    expect(screen.getByRole("button", { name: "Skip for now" })).toBeInTheDocument()
    expect(screen.queryByText("后端失败详情")).not.toBeInTheDocument()
  })

  it("blocks invalid bed counts before submitting", async () => {
    // Given: the nest bed step is open.
    const setupNest = vi.spyOn(client, "setupNest").mockResolvedValue(statusForStep(4))
    renderSetup("en-US", statusForStep(3))

    // When: the bed count is below the supported minimum.
    fireEvent.change(await screen.findByLabelText("Bed count"), { target: { value: "1" } })
    await userEvent.click(screen.getByRole("button", { name: "Save room settings" }))

    // Then: the localized client-side error appears and no API request is made.
    expect(screen.getByRole("alert")).toHaveTextContent("Use 4 to 32 beds.")
    expect(setupNest).not.toHaveBeenCalled()
  })

  it("requires explicit confirmation before enabling the official Ollama install", async () => {
    const user = userEvent.setup()
    renderSetup("en-US", statusForStep(2))

    const install = await screen.findByRole("button", { name: "Download official Ollama" })
    expect(install).toBeDisabled()
    await user.click(screen.getByRole("checkbox", { name: /official Ollama installer/ }))
    await waitFor(() => expect(install).toBeEnabled())
  })

  it("restores refreshed progress and renders the localized finish step", async () => {
    renderSetup("en-US", statusForStep(1))
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Set up the home first.")
    vi.mocked(client.setupStatus).mockResolvedValue(statusForStep(5))

    expect(await screen.findByRole("heading", { level: 1, name: "Ready to finish." }, { timeout: 3_000 })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Enter dashboard" })).toBeEnabled()
  })

  it("hides backend failure detail in English setup errors", async () => {
    // Given: owner creation fails with backend-only detail.
    const user = userEvent.setup()
    vi.spyOn(client, "setup").mockRejectedValue(new ApiError(400, "后端初始化失败详情"))
    renderSetup("en-US", statusForStep(1))

    // When: the English owner form is submitted.
    fireEvent.change(await screen.findByLabelText("Owner account"), { target: { value: "owner" } })
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Owner" } })
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret-pass" } })
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "secret-pass" } })
    await user.click(screen.getByRole("button", { name: "Create owner account" }))

    // Then: the fallback English error is shown instead of backend detail.
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to save setup settings.")
    expect(screen.getByRole("alert")).not.toHaveTextContent("后端初始化失败详情")
  })

  it("recomputes an existing setup error after switching from Chinese to English", async () => {
    const user = userEvent.setup()
    vi.spyOn(client, "setup").mockRejectedValue(new ApiError(400, "后端初始化详情"))
    renderSetup("zh-CN", statusForStep(1))
    fireEvent.change(await screen.findByLabelText("管理员账号"), { target: { value: "owner" } })
    fireEvent.change(screen.getByLabelText("显示名称"), { target: { value: "Owner" } })
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "secret-pass" } })
    fireEvent.change(screen.getByLabelText("确认密码"), { target: { value: "secret-pass" } })

    await user.click(screen.getByRole("button", { name: "创建管理员账号" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("后端初始化详情")
    await user.click(screen.getByRole("combobox", { name: "语言" }))
    await user.click(screen.getByRole("option", { name: "English" }))

    expect(screen.getByRole("alert")).toHaveTextContent("Unable to save setup settings.")
    expect(screen.getByRole("alert")).not.toHaveTextContent("后端初始化详情")
  })
})
