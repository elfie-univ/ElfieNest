import { fireEvent, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

import * as client from "../api/client"
import { createI18n } from "../i18n/config"
import { initializeLocale, type SupportedLocale } from "../i18n/locale"
import { SetupPage } from "./SetupPage"
import type { SetupStatus } from "../api/client"

function statusFor(
  currentStep: number,
  overrides: Partial<SetupStatus> = {},
): SetupStatus {
  const draft = {
    owner_account_id: currentStep > 1 ? "owner" : null,
    display_name: currentStep > 1 ? "Owner" : null,
    password_configured: currentStep > 1,
    use_local_ollama: currentStep > 2 ? true : null,
    ollama_installed: currentStep > 1,
    model_id: currentStep > 2 ? "qwen2.5:0.5b" : null,
    bed_count: currentStep > 3 ? 8 : null,
    owner_configured: currentStep > 1,
    offline_configured: currentStep > 2,
    nest_configured: currentStep > 3,
    locked_at: null,
  } as const
  return {
    complete: false,
    current_step: currentStep,
    need_setup: true,
    locked: false,
    csrf_token: "setup-csrf",
    draft,
    install: {
      phase: "owner",
      action_key: "idle",
      state: "idle",
      progress: 0,
      error_key: null,
    },
    last_error: null,
    task: null,
    steps: [
      { name: "Owner", number: 1, status: currentStep > 1 ? "completed" : currentStep === 1 ? "current" : "pending" },
      { name: "Offline", number: 2, status: currentStep > 2 ? "completed" : currentStep === 2 ? "current" : "pending" },
      { name: "Nest", number: 3, status: currentStep > 3 ? "completed" : currentStep === 3 ? "current" : "pending" },
      { name: "Review", number: 4, status: currentStep === 4 ? "current" : "pending" },
    ],
    ...overrides,
  }
}

function renderSetup(locale: SupportedLocale, status: SetupStatus): void {
  vi.spyOn(client, "setupStatus").mockResolvedValue(status)
  vi.spyOn(client, "setupModelCatalog").mockResolvedValue([
    { model_id: "qwen2.5:0.5b", label: "qwen2.5:0.5b（推荐）", approx_download_mb: 398, recommended: true },
    { model_id: "qwen3.5:0.8b", label: "qwen3.5:0.8b", approx_download_mb: 1024, recommended: false },
    { model_id: "gemma3:270m", label: "gemma3:270m", approx_download_mb: 292, recommended: false },
  ])
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

  it("renders exactly four English configuration steps", async () => {
    renderSetup("en-US", statusFor(1))
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Create the Owner first.")
    for (const label of ["Create Owner account", "Local offline support (optional)", "Nest beds", "Review and install"]) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    expect(screen.queryByText("Model and food")).not.toBeInTheDocument()
  })

  it("saves the Owner draft without calling the legacy immediate setup endpoint", async () => {
    const user = userEvent.setup()
    const save = vi.spyOn(client, "setupSaveOwnerDraft").mockResolvedValue(statusFor(2))
    const legacy = vi.spyOn(client, "setup").mockRejectedValue(new Error("legacy endpoint must not run"))
    renderSetup("en-US", statusFor(1))
    await user.type(await screen.findByLabelText("Owner account"), "owner")
    await user.type(screen.getByLabelText("Display name"), "Owner")
    await user.type(screen.getByLabelText("Password"), "secret-pass")
    await user.type(screen.getByLabelText("Confirm password"), "secret-pass")
    await user.click(screen.getByRole("button", { name: "Save and continue" }))
    expect(save).toHaveBeenCalledWith("owner", "Owner", "secret-pass", "secret-pass", "setup-csrf")
    expect(legacy).not.toHaveBeenCalled()
  })

  it("shows the fixed model dropdown and disables it when local Ollama is unchecked", async () => {
    const user = userEvent.setup()
    const save = vi.spyOn(client, "setupSaveOfflineDraft").mockResolvedValue(statusFor(3))
    renderSetup("en-US", statusFor(2))
    const model = await screen.findByLabelText("Local model")
    expect(within(model).getByText("qwen2.5:0.5b（推荐）")).toBeInTheDocument()
    expect(within(model).getByText("qwen3.5:0.8b")).toBeInTheDocument()
    expect(within(model).getByText("gemma3:270m")).toBeInTheDocument()
    const checkbox = screen.getByRole("checkbox", { name: /Use local Ollama/ })
    await user.click(checkbox)
    expect(model).toBeDisabled()
    await user.click(screen.getByRole("button", { name: "Save and continue" }))
    expect(save).toHaveBeenCalledWith(false, null, "setup-csrf")
  })

  it("renders exactly four review rows and keeps Ollama status inside its row", async () => {
    renderSetup("en-US", statusFor(4))
    const rows = await screen.findAllByTestId("setup-review-row")
    expect(rows).toHaveLength(4)
    expect(rows[1]).toHaveTextContent("Local Ollama")
    expect(rows[1]).toHaveTextContent("Installed")
    expect(screen.queryByText(/emergency food|修复|repair/i)).not.toBeInTheDocument()
  })

  it("shows the disabled-Ollama model summary as not configured", async () => {
    const status = statusFor(4, {
      draft: {
        ...statusFor(4).draft,
        use_local_ollama: false,
        model_id: null,
      },
    })
    renderSetup("en-US", status)
    const rows = await screen.findAllByTestId("setup-review-row")
    expect(rows[2]).toHaveTextContent("Not configured")
    expect(rows[2]).toHaveTextContent("local Ollama is disabled")
  })

  it("locks the page after confirmation and only shows the install progress", async () => {
    const user = userEvent.setup()
    const install = vi.spyOn(client, "setupInstall").mockResolvedValue(statusFor(4, {
      locked: true,
      install: { phase: "ollama", action_key: "ollama.start", state: "running", progress: 30, error_key: null },
    }))
    renderSetup("en-US", statusFor(4))
    await user.click(await screen.findByRole("button", { name: "Confirm configuration and start installation" }))
    expect(install).toHaveBeenCalledWith("setup-csrf")
    expect(await screen.findByRole("progressbar")).toHaveAttribute("aria-valuenow", "30")
    expect(screen.queryByRole("button", { name: /edit|back|cancel/i })).not.toBeInTheDocument()
  })
})
