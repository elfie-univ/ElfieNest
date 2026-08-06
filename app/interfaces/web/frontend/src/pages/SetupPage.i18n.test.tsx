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

  it("renders the English welcome page before the configuration steps", async () => {
    renderSetup("en-US", statusFor(1))
    expect(await screen.findByRole("heading", { level: 1, name: "Build a home on Earth for an Elfie from Elfaria." })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Begin" })).toBeInTheDocument()
    expect(screen.getByTestId("setup-welcome-art")).toBeInTheDocument()
    expect(screen.getByTestId("setup-welcome-house-drawing")).toBeInTheDocument()
    expect(screen.getByTestId("setup-welcome-radar")).toBeInTheDocument()
    expect(screen.getByTestId("setup-welcome-radar").querySelector(".setup-welcome__radar-body-path")).toBeInTheDocument()
    expect(screen.getByTestId("setup-welcome-radar-rings")).toBeInTheDocument()
    const signal = screen.getByTestId("setup-welcome-signal")
    expect(signal.querySelectorAll("circle")).toHaveLength(3)
    expect(signal.querySelector("circle")).toHaveAttribute("cx", "208.4")
    expect(signal.querySelector("circle")).toHaveAttribute("cy", "37.4")
    expect(screen.getByTestId("setup-welcome-ground-ripples")).toBeInTheDocument()
    expect(screen.getByTestId("setup-welcome-beam")).toBeInTheDocument()
    expect(screen.getByTestId("setup-welcome-fox")).toHaveAttribute("src", expect.stringContaining("elfienest-fox-transparent.png"))
    expect(screen.getByTestId("setup-welcome-fox-eye-glint")).toBeInTheDocument()
    expect(screen.getByTestId("setup-welcome-final-logo")).toHaveAttribute("src", expect.stringContaining("elfienest-logo-mark-transparent.png"))
    expect(screen.queryByText("Create Owner account")).not.toBeInTheDocument()
  })

  it("keeps the supplied house geometry in its native SVG coordinates", async () => {
    renderSetup("en-US", statusFor(1))

    const drawing = await screen.findByTestId("setup-welcome-house-drawing")
    const svg = drawing.closest("svg")
    const fill = screen.getByTestId("setup-welcome-house-fill")
    const roofPath = screen.getByTestId("setup-welcome-house-roof-path")
    const bodyPath = screen.getByTestId("setup-welcome-house-body-path")
    const chimneyBlock = screen.getByTestId("setup-welcome-house-chimney-block")
    const chimneyWipe = screen.getByTestId("setup-welcome-house-chimney-wipe")
    const finalFill = screen.getByTestId("setup-welcome-house-final-fill")

    expect(svg).toHaveAttribute("viewBox", "0 0 270.93332 270.93332")
    expect(drawing.querySelectorAll(".setup-welcome__house-path")).toHaveLength(2)
    expect(drawing.querySelectorAll(".setup-welcome__house-phase-block")).toHaveLength(3)
    expect(roofPath).toHaveAttribute(
      "d",
      expect.stringMatching(/^M 247\.74802,119\.80303 136\.08694,27\.333702 24\.425861,122\.12931/),
    )
    expect(bodyPath).toHaveAttribute(
      "d",
      expect.stringMatching(/^M 24\.425861,122\.12931 52\.341131,98\.285013 53\.504266,237\.27979/),
    )
    expect(roofPath).toHaveAttribute("pathLength", "1")
    expect(bodyPath).toHaveAttribute("pathLength", "1")
    expect(chimneyBlock).toHaveAttribute("d", expect.stringContaining("192.67816 51.229431"))
    expect(chimneyWipe.tagName.toLowerCase()).toBe("rect")
    expect(finalFill).toHaveAttribute("d", fill.getAttribute("d"))
    expect(finalFill).not.toHaveAttribute("mask")
    expect(fill).not.toHaveAttribute("transform")
  })

  it("reveals exactly four English configuration steps after the welcome action", async () => {
    const user = userEvent.setup()
    renderSetup("en-US", statusFor(1))
    await user.click(await screen.findByRole("button", { name: "Begin" }))

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Create the Owner first")
    for (const label of ["Create Owner account", "Local offline support (optional)", "Nest beds", "Review and install"]) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    expect(screen.queryByTestId("setup-welcome-art")).not.toBeInTheDocument()
    expect(screen.queryByText("Model and food")).not.toBeInTheDocument()
    expect(screen.queryByText("Create the single Owner account. You can change its password in this step.", { exact: true })).not.toBeInTheDocument()
  })

  it("keeps the welcome page in the detected English locale before setup starts", async () => {
    renderSetup("en-US", statusFor(1))

    const language = await screen.findByRole("combobox", { name: "Language" })
    expect(language).toHaveTextContent("English")
    expect(await screen.findByRole("heading", { level: 1, name: "Build a home on Earth for an Elfie from Elfaria." })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Begin" })).toBeInTheDocument()
  })

  it("renders the requested Chinese welcome copy when Chinese is detected", async () => {
    renderSetup("zh-CN", statusFor(1))

    expect(await screen.findByRole("heading", { level: 1, name: "为来自 Elfaria 的精灵，在地球上建立一个家" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "开始" })).toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: "语言" })).toHaveTextContent("简体中文")
  })

  it("uses the full transparent logo as the setup rail brand", async () => {
    const user = userEvent.setup()
    renderSetup("en-US", statusFor(1))
    await user.click(await screen.findByRole("button", { name: "Begin" }))

    const logo = await screen.findByRole("img", { name: "ELFIE NEST" })
    expect(logo).toHaveAttribute(
      "src",
      expect.stringContaining("elfienest-full-logo-transparent.png"),
    )
    expect(screen.queryByText("ELFIE NEST")).not.toBeInTheDocument()
  })

  it("saves the Owner draft without calling the legacy immediate setup endpoint", async () => {
    const user = userEvent.setup()
    const save = vi.spyOn(client, "setupSaveOwnerDraft").mockResolvedValue(statusFor(2))
    const legacy = vi.spyOn(client, "setup").mockRejectedValue(new Error("legacy endpoint must not run"))
    renderSetup("en-US", statusFor(1))
    await user.click(await screen.findByRole("button", { name: "Begin" }))
    await user.type(await screen.findByRole("textbox", { name: "Owner account" }), "owner")
    await user.type(screen.getByRole("textbox", { name: "Display name" }), "Owner")
    await user.type(within(screen.getByRole("group", { name: "Password" })).getByLabelText("Password"), "secret-pass")
    await user.type(within(screen.getByRole("group", { name: "Confirm password" })).getByLabelText("Confirm password"), "secret-pass")
    await user.click(screen.getByRole("button", { name: "Save and continue" }))
    expect(save).toHaveBeenCalledWith("owner", "Owner", "secret-pass", "secret-pass", "setup-csrf")
    expect(legacy).not.toHaveBeenCalled()
  })

  it("uses shared controls and disables the model selector when local Ollama is unchecked", async () => {
    const user = userEvent.setup()
    const save = vi.spyOn(client, "setupSaveOfflineDraft").mockResolvedValue(statusFor(3))
    renderSetup("en-US", statusFor(2))
    const model = await screen.findByRole("combobox", { name: "Local model" })
    expect(model).toHaveAttribute("data-slot", "select-trigger")
    expect(model).toHaveTextContent("qwen2.5:0.5b（推荐）")
    await user.click(model)
    expect(screen.getByRole("option", { name: "qwen2.5:0.5b（推荐）" })).toBeInTheDocument()
    expect(screen.getByRole("option", { name: "qwen3.5:0.8b" })).toBeInTheDocument()
    expect(screen.getByRole("option", { name: "gemma3:270m" })).toBeInTheDocument()
    await user.keyboard("{Escape}")
    const checkbox = screen.getByRole("checkbox", { name: /Use local Ollama/ })
    expect(checkbox).toHaveAttribute("data-slot", "checkbox")
    await user.click(checkbox)
    expect(model).toBeDisabled()
    await user.click(screen.getByRole("button", { name: "Save and continue" }))
    expect(save).toHaveBeenCalledWith(false, null, "setup-csrf")
  })

  it("shows reusable and pending Ollama states with distinct status styles", async () => {
    renderSetup("en-US", statusFor(2))
    const installedStatus = await screen.findByText("Installed · reusable")
    expect(installedStatus).toHaveClass("setup-hint--status", "setup-hint--installed")

    renderSetup("en-US", statusFor(2, {
      draft: { ...statusFor(2).draft, ollama_installed: false },
    }))
    const pendingStatus = await screen.findByText("Not installed · handled during setup")
    expect(pendingStatus).toHaveClass("setup-hint--status", "setup-hint--missing")
  })

  it("renders exactly four review rows and keeps Ollama status inside its row", async () => {
    renderSetup("en-US", statusFor(4))
    const rows = await screen.findAllByTestId("setup-review-row")
    expect(rows).toHaveLength(4)
    expect(rows[1]).toHaveTextContent("Local Ollama")
    expect(rows[1]).toHaveTextContent("Installed")
    expect(screen.queryByText(/emergency food|修复|repair/i)).not.toBeInTheDocument()
  })

  it("allows returning to a saved step before final confirmation", async () => {
    const user = userEvent.setup()
    renderSetup("en-US", statusFor(4))

    // When: a saved step is selected from the setup rail.
    const ownerStep = await screen.findByRole("button", { name: /Create Owner account/ })
    await user.click(ownerStep)

    // Then: the wizard returns to that step without changing the saved flow.
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Create the Owner first")
    expect(ownerStep).toHaveAttribute("aria-current", "step")
    expect(ownerStep.closest("li")).toHaveClass("setup-step--current")
  })

  it("uses compact horizontal rows for the Owner form", async () => {
    const user = userEvent.setup()
    renderSetup("en-US", statusFor(1))
    await user.click(await screen.findByRole("button", { name: "Begin" }))

    // Then: the four Owner fields share the compact form layout contract.
    expect((await screen.findByRole("textbox", { name: "Owner account" })).closest("form")).toHaveClass("setup-form--owner")
    for (const label of ["Owner account", "Display name", "Password", "Confirm password"]) {
      const field = screen.getByRole("group", { name: label })
      const input = within(field).getByLabelText(label)
      expect(input).toHaveAttribute("data-slot", "input")
      expect(input.closest('[data-field-row="true"]')).toBeInTheDocument()
    }
  })

  it("uses a compact bed-count row and rejects values outside 4 to 32", async () => {
    const user = userEvent.setup()
    renderSetup("en-US", statusFor(3))
    const bedCount = await screen.findByRole("textbox", { name: "Bed count" })

    // When: the user enters a count above the supported range.
    await user.clear(bedCount)
    await user.type(bedCount, "45")

    // Then: the field explains the range and saving is unavailable.
    expect(bedCount.closest("section")).toHaveClass("setup-form--bed-count")
    expect(bedCount).toHaveAttribute("data-slot", "input")
    expect(bedCount.closest('[data-field-row="true"]')).toBeInTheDocument()
    expect(bedCount).toHaveAttribute("aria-invalid", "true")
    expect(screen.getByText("Use 4 to 32 beds.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Save bed settings" })).toBeDisabled()
  })

  it("removes the large explanatory callout from offline support", async () => {
    renderSetup("en-US", statusFor(2))
    const model = await screen.findByRole("combobox", { name: "Local model" })
    expect(model).toBeInTheDocument()
    expect(model.closest("section")).toHaveClass("setup-form--offline")
    expect(screen.getByRole("checkbox", { name: /Use local Ollama/ }).closest(".setup-check--row")).toHaveClass("setup-check--row")
    expect(screen.queryByText(/This step only saves local offline support configuration/)).not.toBeInTheDocument()
  })

  it("keeps configured passwords masked and sends a newly entered replacement", async () => {
    const user = userEvent.setup()
    const save = vi.spyOn(client, "setupSaveOwnerDraft").mockResolvedValue(statusFor(2))
    renderSetup("en-US", statusFor(4))
    await user.click(await screen.findByRole("button", { name: /Create Owner account/ }))

    const password = within(screen.getByRole("group", { name: "Password" })).getByLabelText("Password")
    const confirmation = within(screen.getByRole("group", { name: "Confirm password" })).getByLabelText("Confirm password")
    expect(password).toHaveValue("")
    expect(confirmation).toHaveValue("")
    expect(password).toHaveAttribute("placeholder", "••••••••")
    expect(confirmation).toHaveAttribute("placeholder", "••••••••")

    await user.type(password, "new-secret")
    await user.type(confirmation, "new-secret")
    await user.click(screen.getByRole("button", { name: "Save and continue" }))

    expect(save).toHaveBeenCalledWith("owner", "Owner", "new-secret", "new-secret", "setup-csrf")
  })

  it("removes the large explanatory callout from nest beds", async () => {
    renderSetup("en-US", statusFor(3))
    expect(await screen.findByRole("textbox", { name: "Bed count" })).toBeInTheDocument()
    expect(screen.queryByText(/The Nest keeps 4 to 32 beds/)).not.toBeInTheDocument()
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
