import { act, fireEvent, render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { createI18n } from "../i18n/config"
import { ManageMonitorPanel } from "./ManageMonitorPanel"
import { ToastProvider } from "./ui/toast"

const api = vi.hoisted(() => ({ ownerRead: vi.fn() }))

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>()
  return { ...actual, ownerRead: api.ownerRead }
})

type MonitorFixture = {
  readonly healthStatus: string
  readonly runtimeStatus: string
  readonly runtimeNotes: readonly string[]
  readonly unassignedElfie?: boolean
}

const healthyFixture: MonitorFixture = {
  healthStatus: "ok",
  runtimeStatus: "ok",
  runtimeNotes: [],
}

const attentionFixture: MonitorFixture = {
  healthStatus: "ok",
  runtimeStatus: "degraded",
  runtimeNotes: ["The runtime database is unavailable."],
}

const unassignedBedFixture: MonitorFixture = {
  ...healthyFixture,
  unassignedElfie: true,
}

describe("ManageMonitorPanel persistent runtime status", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
  })

  it("keeps a partial-load failure visible after timers and retries into recovery", async () => {
    api.ownerRead.mockImplementation(async (path: string) => {
      if (path === "/api/health") throw new Error("network unavailable")
      return monitorPayload(path, healthyFixture)
    })
    renderPanel()

    expect(screen.getAllByRole("button", { name: "Refresh status" })).toHaveLength(1)
    expect(document.querySelector(".monitor-panel")).toHaveClass("manage-card", "manage-card--wide")
    expect(await screen.findByRole("alert")).toHaveTextContent("Some status data is temporarily unavailable.")
    vi.useFakeTimers()
    act(() => { vi.advanceTimersByTime(60000) })
    expect(screen.getByRole("alert")).toHaveTextContent("Some status data is temporarily unavailable.")

    vi.useRealTimers()
    mockSnapshot(healthyFixture)
    fireEvent.click(lastButton("Refresh status"))

    expect(await screen.findByText("Healthy")).toBeInTheDocument()
    expect(await screen.findByText("Runtime status recovered.")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("keeps non-ok runtime attention persistent and dedupes repeated recovery", async () => {
    mockSnapshot(attentionFixture)
    renderPanel()

    expect(await screen.findByRole("alert")).toHaveTextContent("Items need attention")
    vi.useFakeTimers()
    act(() => { vi.advanceTimersByTime(60000) })
    expect(screen.getByRole("alert")).toHaveTextContent("Items need attention")

    vi.useRealTimers()
    mockSnapshot(healthyFixture)
    fireEvent.click(lastButton("Refresh status"))
    expect(await screen.findByText("Runtime status recovered.")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()

    fireEvent.click(lastButton("Refresh status"))
    await screen.findByText("Services healthy")
    expect(screen.getAllByText("Runtime status recovered.")).toHaveLength(1)
  })

  it("keeps available cards visible while a refresh source is unavailable", async () => {
    mockSnapshot(healthyFixture)
    renderPanel()

    expect(await screen.findByText("Services healthy")).toBeInTheDocument()
    api.ownerRead.mockImplementation(async (path: string) => {
      if (path === "/api/owner/nest/rooms") throw new Error("rooms unavailable")
      return monitorPayload(path, healthyFixture)
    })
    fireEvent.click(screen.getByRole("button", { name: "Refresh status" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Some status data is temporarily unavailable.")
    expect(screen.getByText("Users")).toBeInTheDocument()
    expect(screen.getByText("2 online")).toBeInTheDocument()
    expect(screen.getByText("Model service details")).toBeInTheDocument()
  })

  it("keeps bed assignment notices out of system health", async () => {
    mockSnapshot(unassignedBedFixture)
    renderPanel()

    expect(await screen.findByText("Services healthy")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(screen.getByText(/no assigned bed/)).toBeInTheDocument()
  })
})

function renderPanel(): void {
  const i18n = createI18n()
  void i18n.changeLanguage("en-US")
  render(<I18nextProvider i18n={i18n}><ToastProvider><ManageMonitorPanel /></ToastProvider></I18nextProvider>)
}

function mockSnapshot(fixture: MonitorFixture): void {
  api.ownerRead.mockImplementation(async (path: string) => monitorPayload(path, fixture))
}

function monitorPayload(path: string, fixture: MonitorFixture): unknown {
  switch (path) {
    case "/api/health":
      return { status: fixture.healthStatus, engine_ready: true, godot_web_ready: true, godot_runtime_ready: true }
    case "/api/owner/runtime/status":
      return {
        status: fixture.runtimeStatus,
        providers: { total: 1, active: 1, inactive: 0 },
        models: { total: 1, visible: 1, hidden: 0 },
        fallback: { provider: "ollama", configured: true },
        observer: { event_count: 1, last_event: null },
        notes: fixture.runtimeNotes,
      }
    case "/api/owner/users":
      return [{ presence: "online" }, { presence: "online" }]
    case "/api/owner/elfies":
      return [
        { elfie_id: "elfie-1", profile: { online_status: "online" } },
        { elfie_id: "elfie-2", profile: { online_status: "offline" } },
      ]
    case "/api/owner/nest/rooms":
      return [{ beds: fixture.unassignedElfie ? [{ occupant_id: "elfie-1" }] : [{ occupant_id: "elfie-1" }, { occupant_id: "elfie-2" }] }]
    case "/api/owner/providers/connections":
      return [{
        catalog_id: "ollama",
        alias: "Ollama",
        enabled: true,
        archived: false,
        verification: { status: "passed" },
        models: [{ available: true, hidden: false, retired: false }],
      }]
    case "/api/owner/providers/ollama":
      return { state: "healthy", recommended_model: "qwen2.5:0.5b", installed_model_count: 1 }
    default:
      return { endpoint: "https://raw.example/v1" }
  }
}

function lastButton(name: string): HTMLElement {
  const buttons = screen.getAllByRole("button", { name })
  const button = buttons.at(-1)
  if (!button) throw new Error(`Missing button: ${name}`)
  return button
}
