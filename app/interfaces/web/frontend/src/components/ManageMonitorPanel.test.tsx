import { act, fireEvent, render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { createI18n } from "../i18n/config"
import { ManageMonitorPanel } from "./ManageMonitorPanel"
import { ToastProvider } from "./ui/toast"

const api = vi.hoisted(() => ({ ownerRead: vi.fn() }))

vi.mock("../api/client", () => ({ ownerRead: api.ownerRead }))

const healthyStatus = {
  fallback: { configured: true, provider: "provider/qwen3:4b" },
  models: { hidden: 0, total: 1, visible: 1 },
  notes: [],
  observer: { event_count: 1, last_event: "runtime-ready" },
  providers: { active: 1, inactive: 0, total: 1 },
  status: "ok",
} as const

const attentionStatus = {
  ...healthyStatus,
  notes: ["The runtime database is unavailable."],
  providers: { active: 0, inactive: 1, total: 1 },
  status: "degraded",
} as const

describe("ManageMonitorPanel persistent runtime status", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
  })

  it("keeps a request failure visible after timers and retries into recovery", async () => {
    api.ownerRead.mockRejectedValueOnce(new Error("network unavailable"))
    renderPanel()

    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load management data.")
    vi.useFakeTimers()
    act(() => { vi.advanceTimersByTime(60000) })
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to load management data.")

    vi.useRealTimers()
    api.ownerRead.mockResolvedValueOnce(healthyStatus)
    const retry = lastButton("Refresh status")
    fireEvent.click(retry)

    expect(await screen.findByText("Healthy")).toBeInTheDocument()
    expect(screen.getByText("Runtime status recovered.")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("keeps non-ok health attention persistent and dedupes repeated recovery", async () => {
    api.ownerRead.mockResolvedValueOnce(attentionStatus)
    renderPanel()

    expect(await screen.findByRole("alert")).toHaveTextContent("Needs attention")
    vi.useFakeTimers()
    act(() => { vi.advanceTimersByTime(60000) })
    expect(screen.getByRole("alert")).toHaveTextContent("Needs attention")

    vi.useRealTimers()
    api.ownerRead.mockResolvedValue(healthyStatus)
    fireEvent.click(lastButton("Refresh status"))
    expect(await screen.findByText("Runtime status recovered.")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()

    fireEvent.click(lastButton("Refresh status"))
    await screen.findByText("Healthy")
    expect(screen.getAllByText("Runtime status recovered.")).toHaveLength(1)
  })

  it("keeps the last metrics visible while a refresh failure is persistent", async () => {
    api.ownerRead.mockResolvedValueOnce(healthyStatus)
    renderPanel()

    expect(await screen.findByText("1/1")).toBeInTheDocument()
    api.ownerRead.mockRejectedValueOnce(new Error("network unavailable"))
    fireEvent.click(lastButton("Refresh status"))

    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load management data.")
    expect(screen.getByText("1/1")).toBeInTheDocument()
    expect(screen.getByText("Needs attention")).toBeInTheDocument()
  })
})

function renderPanel(): void {
  const i18n = createI18n()
  void i18n.changeLanguage("en-US")
  render(<I18nextProvider i18n={i18n}><ToastProvider><ManageMonitorPanel elfieCount={2} /></ToastProvider></I18nextProvider>)
}

function lastButton(name: string): HTMLElement {
  const buttons = screen.getAllByRole("button", { name })
  const button = buttons.at(-1)
  if (!button) throw new Error(`Missing button: ${name}`)
  return button
}
