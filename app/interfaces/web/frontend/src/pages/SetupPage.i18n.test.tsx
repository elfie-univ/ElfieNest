import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

import * as client from "../api/setup"
import { createI18n } from "../i18n/config"
import { initializeLocale, type SupportedLocale } from "../i18n/locale"
import { SetupPage } from "./SetupPage"
import type { SetupStatus } from "../api/setup"

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
    steps: [
      { name: "Owner", number: 1, status: currentStep > 1 ? "completed" : currentStep === 1 ? "current" : "pending", retry_action: null },
      { name: "Offline", number: 2, status: currentStep > 2 ? "completed" : currentStep === 2 ? "current" : "pending", retry_action: null },
      { name: "Nest", number: 3, status: currentStep > 3 ? "completed" : currentStep === 3 ? "current" : "pending", retry_action: null },
      { name: "Review", number: 4, status: currentStep === 4 ? "current" : "pending", retry_action: null },
    ],
    ...overrides,
  }
}

function renderSetup(
  locale: SupportedLocale,
  status: SetupStatus,
  ollama: client.SetupOllamaObservation = {
    endpoint: "http://127.0.0.1:11434",
    platform: "darwin",
    state: "stopped",
    version: null,
  },
): void {
  vi.spyOn(client, "setupStatus").mockResolvedValue(status)
  vi.spyOn(client, "setupInspectOllama").mockResolvedValue(ollama)
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
    expect(await screen.findByRole("heading", { level: 1, name: "Build a home on Earth for your Elfie from Elfaria" })).toBeInTheDocument()
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
    expect(signal.querySelector("circle")).toHaveAttribute("r", "8.1")
    expect(screen.getByTestId("setup-welcome-radar-rings").querySelector("circle")).toHaveAttribute("r", "5.4")
    const groundRipples = screen.getByTestId("setup-welcome-ground-ripples")
    expect(groundRipples).toBeInTheDocument()
    expect(groundRipples.querySelector("ellipse")).toHaveAttribute("cx", "137.8")
    expect(groundRipples.querySelector("ellipse")).toHaveAttribute("cy", "220.5")
    const beam = screen.getByTestId("setup-welcome-beam")
    expect(beam).toBeInTheDocument()
    expect(beam.querySelector("path")).toHaveAttribute("d", expect.stringContaining("137.8 220.5"))
    expect(screen.getByTestId("setup-welcome-fox")).toHaveAttribute("src", expect.stringContaining("elfienest-fox-transparent.png"))
    expect(screen.getByTestId("setup-welcome-fox-eye-glint")).toBeInTheDocument()
    expect(screen.getByTestId("setup-welcome-final-logo")).toHaveAttribute("src", expect.stringContaining("elfienest-logo-mark-transparent.png"))
    const title = screen.getByRole("heading", { level: 1 })
    expect(title).toHaveAttribute("aria-label", "Build a home on Earth for your Elfie from Elfaria")
    expect(title.querySelectorAll(".setup-welcome__title-char")).toHaveLength("Build a home on Earth for your Elfie from Elfaria".length)
    expect(screen.queryByText("Create Owner account")).not.toBeInTheDocument()
  })

  it("finishes the welcome copy at seven seconds with no locale-dependent action gap", async () => {
    renderSetup("en-US", statusFor(1))

    const title = await screen.findByRole("heading", { level: 1 })
    const characters = title.querySelectorAll(".setup-welcome__title-char")
    const action = screen.getByRole("button", { name: "Begin" }) as HTMLButtonElement

    expect((characters[0] as HTMLElement).style.animationDelay).toBe("6s")
    expect((characters[characters.length - 1] as HTMLElement).style.animationDelay).toBe("6.72s")
    expect(action.style.animationDelay).toBe("7s")
  })

  it("keeps the owner form hidden while the initial setup status is loading", async () => {
    let resolveStatus: (status: SetupStatus) => void = () => undefined
    vi.spyOn(client, "setupStatus").mockReturnValue(new Promise((resolve) => {
      resolveStatus = resolve
    }))
    vi.spyOn(client, "setupModelCatalog").mockResolvedValue([])
    const instance = createI18n()
    initializeLocale(instance, {
      browserLanguages: ["en-US"],
      documentElement: document.documentElement,
      storage: localStorage,
    })
    render(
      <I18nextProvider i18n={instance}>
        <SetupPage />
      </I18nextProvider>,
    )

    expect(screen.getByTestId("setup-welcome-art")).toBeInTheDocument()
    expect(screen.queryByRole("textbox", { name: "Owner account" })).not.toBeInTheDocument()

    resolveStatus(statusFor(1))
    await waitFor(() => expect(screen.getByRole("button", { name: "Begin" })).toBeEnabled())
    expect(screen.queryByRole("textbox", { name: "Owner account" })).not.toBeInTheDocument()
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
    expect(svg).toHaveAttribute("data-house-source", "elfienest-house.svg")
    expect(drawing.querySelectorAll(".setup-welcome__house-path")).toHaveLength(2)
    expect(drawing.querySelectorAll(".setup-welcome__house-phase-block")).toHaveLength(3)
    expect(roofPath).toHaveAttribute(
      "d",
      expect.stringMatching(/^M 247\.74802 119\.80303 L 136\.08694 27\.333702 L 24\.425861 122\.12931 L 52\.341131 98\.285013$/),
    )
    expect(bodyPath).toHaveAttribute(
      "d",
      expect.stringMatching(/^M 52\.341131 98\.285013 L 53\.504266 237\.27979 L 220\.99589 236\.69822 L 224\.4853 100\.02972 L 201\.80414 80\.837968$/),
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
    expect(await screen.findByRole("heading", { level: 1, name: "Build a home on Earth for your Elfie from Elfaria" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Begin" })).toBeInTheDocument()
  })

  it("renders the requested Chinese welcome copy when Chinese is detected", async () => {
    renderSetup("zh-CN", statusFor(1))

    expect(await screen.findByRole("heading", { level: 1, name: "为来自 Elfaria 的精灵在地球上建一个家" })).toBeInTheDocument()
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

  it("saves the Owner draft through the draft-based setup API", async () => {
    const user = userEvent.setup()
    const save = vi.spyOn(client, "setupSaveOwnerDraft").mockResolvedValue(statusFor(2))
    renderSetup("en-US", statusFor(1))
    await user.click(await screen.findByRole("button", { name: "Begin" }))
    await user.type(await screen.findByRole("textbox", { name: "Owner account" }), "owner")
    await user.type(screen.getByRole("textbox", { name: "Display name" }), "Owner")
    await user.type(within(screen.getByRole("group", { name: "Password" })).getByLabelText("Password"), "secret-pass")
    await user.type(within(screen.getByRole("group", { name: "Confirm password" })).getByLabelText("Confirm password"), "secret-pass")
    await user.click(screen.getByRole("button", { name: "Save and continue" }))
    expect(save).toHaveBeenCalledWith("owner", "Owner", "secret-pass", "secret-pass", "setup-csrf")
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

  it("saves enabled local Ollama with the selected model for final installation", async () => {
    const user = userEvent.setup()
    const save = vi.spyOn(client, "setupSaveOfflineDraft").mockResolvedValue(statusFor(3))
    renderSetup("en-US", statusFor(2))

    await screen.findByRole("combobox", { name: "Local model" })
    await user.click(screen.getByRole("button", { name: "Save and continue" }))

    expect(save).toHaveBeenCalledWith(true, "qwen2.5:0.5b", "setup-csrf")
  })

  it("shows reusable and pending Ollama states with distinct status styles", async () => {
    renderSetup("en-US", statusFor(2))
    const installedStatus = await screen.findByText("Installed · reusable")
    expect(installedStatus).toHaveClass("setup-hint--status", "setup-hint--installed")

    renderSetup(
      "en-US",
      statusFor(2, {
        draft: { ...statusFor(2).draft, ollama_installed: false },
      }),
      { endpoint: null, platform: "darwin", state: "absent", version: null },
    )
    const pendingStatus = await screen.findByText("Not installed · handled during setup")
    expect(pendingStatus).toHaveClass("setup-hint--status", "setup-hint--missing")
  })

  it("guides Linux installation in a terminal and rechecks before continuing", async () => {
    const user = userEvent.setup()
    renderSetup(
      "en-US",
      statusFor(2, {
        draft: { ...statusFor(2).draft, ollama_installed: false },
      }),
      { endpoint: null, platform: "linux", state: "absent", version: null },
    )

    expect(await screen.findByText("Install Ollama in a terminal first")).toBeInTheDocument()
    expect(screen.getByText("curl -fsSL https://ollama.com/install.sh | sh")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Save and continue" })).toBeDisabled()

    vi.mocked(client.setupInspectOllama).mockResolvedValue({
      endpoint: "http://127.0.0.1:11434",
      platform: "linux",
      state: "healthy",
      version: "0.12.0",
    })
    await user.click(screen.getByRole("button", { name: "I've installed Ollama — check again" }))

    await waitFor(() => {
      expect(screen.getByText("Installed · reusable")).toBeInTheDocument()
      expect(screen.getByRole("button", { name: "Save and continue" })).toBeEnabled()
    })
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

  it("locks the page after confirmation and exposes cancellation", async () => {
    const user = userEvent.setup()
    const running = statusFor(4, {
      locked: true,
      install: { phase: "ollama", action_key: "ollama.start", state: "running", progress: 30, error_key: null },
    })
    const install = vi.spyOn(client, "setupInstall").mockResolvedValue(running)
    const cancel = vi.spyOn(client, "setupCancel").mockResolvedValue(statusFor(4, {
      install: { phase: "ollama", action_key: "cancelled", state: "cancelled", progress: 30, error_key: "setup.install.cancelled" },
    }))
    renderSetup("en-US", statusFor(4))
    await user.click(await screen.findByRole("button", { name: "Confirm configuration and start installation" }))
    expect(install).toHaveBeenCalledWith("setup-csrf")
    expect(await screen.findByRole("progressbar")).toHaveAttribute("aria-valuenow", "30")
    await user.click(screen.getByRole("button", { name: "Cancel installation" }))
    expect(cancel).toHaveBeenCalledWith("setup-csrf")
    expect(await screen.findByText("Installation cancelled. You can adjust the remaining settings and try again.")).toBeInTheDocument()
  })

  it("shows persisted failure detail after unlocking safe configuration fields", async () => {
    const failed = statusFor(4, {
      install: { phase: "model", action_key: "model.download", state: "failed", progress: 50, error_key: "setup.install.failed" },
      last_error: "The model download timed out.",
    })
    renderSetup("en-US", failed)

    expect(await screen.findByRole("alert")).toHaveTextContent("The model download timed out.")
    const rows = await screen.findAllByTestId("setup-review-row")
    expect(within(rows[0]).queryByRole("button", { name: "Modify" })).not.toBeInTheDocument()
    expect(within(rows[1]).getByRole("button", { name: "Modify" })).toBeInTheDocument()
  })
})
