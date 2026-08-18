import { act, fireEvent, render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { createI18n } from "../i18n/config"
import { ManageMonitorPanel } from "./ManageMonitorPanel"
import { ToastProvider } from "./ui/toast"

const api = vi.hoisted(() => ({ ownerRead: vi.fn() }))

vi.mock("../api/http", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/http")>()
  return { ...actual, ownerRead: api.ownerRead, requestJson: api.ownerRead }
})

type MonitorFixture = {
  readonly healthStatus: string
  readonly runtimeStatus: string
  readonly noCoreModel?: boolean
  readonly noFoods?: boolean
  readonly emergencyDegraded?: boolean
  readonly unassignedElfie?: boolean
  readonly remoteSubscription?: boolean
  readonly localOnlyCommon?: boolean
}

const healthyFixture: MonitorFixture = {
  healthStatus: "ok",
  runtimeStatus: "ok",
}

const attentionFixture: MonitorFixture = {
  healthStatus: "ok",
  runtimeStatus: "degraded",
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

    expect((await screen.findAllByText("Healthy")).length).toBeGreaterThan(0)
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
    expect(await screen.findByText("AI service details")).toBeInTheDocument()
    api.ownerRead.mockImplementation(async (path: string) => {
      if (path === "/api/v1/admin/nest/rooms") throw new Error("rooms unavailable")
      return monitorPayload(path, healthyFixture)
    })
    fireEvent.click(screen.getByRole("button", { name: "Refresh status" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Some status data is temporarily unavailable.")
    expect(screen.getByText("Users")).toBeInTheDocument()
    expect(screen.getByText("2 online")).toBeInTheDocument()
    expect(screen.getByText("AI service details")).toBeInTheDocument()
  })

  it("does not call a configured service unconfigured when no model core flag is present", async () => {
    mockSnapshot({ ...healthyFixture, noCoreModel: true, noFoods: true })
    renderPanel()

    expect(await screen.findByText("Needs attention")).toBeInTheDocument()
    expect(screen.queryByText("No AI service configured")).not.toBeInTheDocument()
    expect(screen.getByText("Ollama")).toBeInTheDocument()
  })

  it("keeps a Provider account pass separate from pending model evidence", async () => {
    api.ownerRead.mockImplementation(async (path: string) => {
      const payload = monitorPayload(path, healthyFixture)
      if (path === "/api/v1/admin/model-providers/connections") return { items: [{
        catalog_id: "openai",
        alias: "OpenAI",
        enabled: true,
        archived: false,
        verification: { status: "passed" },
        model_counts: { total: 1, enabled: 1, in_use: 0, available: 0, degraded: 0, pending: 1, unavailable: 0 },
        models: [{ available: false, hidden: false, retired: false, verification: { availability_status: "unknown" } }],
      }] }
      return payload
    })
    renderPanel()

    expect(await screen.findByText("0/1 models available")).toBeInTheDocument()
    expect(screen.getByText("AI service").closest("article")).toHaveTextContent("Needs attention")
    expect(screen.queryByText("1/1 models available")).not.toBeInTheDocument()
  })

  it("shows supported local models and Food status without exposing unrelated Ollama installs", async () => {
    mockSnapshot(healthyFixture)
    renderPanel()

    expect(await screen.findByText("1/1 models available")).toBeInTheDocument()
    expect(screen.queryByText("1/2 models available")).not.toBeInTheDocument()
    const foodRegion = screen.getByRole("region", { name: "Food" })
    expect(withinFood(foodRegion, "Common")).toHaveTextContent("Healthy")
    expect(withinFood(foodRegion, "Emergency")).toHaveTextContent("Healthy")
    const systemEvents = screen.getByText("System events").closest("section")
    const aiService = screen.getByText("AI service details").closest("section")
    expect(systemEvents).not.toBeNull()
    expect(aiService).not.toBeNull()
    expect(systemEvents?.compareDocumentPosition(aiService as Node) ?? 0).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
  })

  it("keeps Ollama first in the AI service details", async () => {
    mockSnapshot({ ...healthyFixture, remoteSubscription: true })
    renderPanel()

    await screen.findByText("Volcengine Coding Plan")
    const services = document.querySelector(".monitor-service-list")
    expect(services).not.toBeNull()
    const rows = [...(services as HTMLElement).querySelectorAll("li")]
    expect(rows[0]).toHaveTextContent("Ollama")
    expect(rows[1]).toHaveTextContent("Volcengine Coding Plan")
  })

  it("shows interstellar travel as enabled when the common Food has a usable remote subscription", async () => {
    mockSnapshot({ ...healthyFixture, remoteSubscription: true })
    renderPanel()

    const region = await screen.findByRole("region", { name: "Interstellar travel" })
    expect(region).toHaveTextContent("Enabled")
    expect(region).not.toHaveTextContent("Please provide at least one valid model subscription")
  })

  it("does not count a local Ollama model as a valid interstellar subscription", async () => {
    mockSnapshot({ ...healthyFixture, localOnlyCommon: true })
    renderPanel()

    const region = await screen.findByRole("region", { name: "Interstellar travel" })
    expect(region).toHaveTextContent("Not enabled")
    expect(region).toHaveTextContent("Please provide at least one valid model subscription")
  })

  it("shows only abnormal Food details when the AI service needs attention", async () => {
    mockSnapshot({ ...healthyFixture, emergencyDegraded: true })
    renderPanel()

    const foodRegion = await screen.findByRole("region", { name: "Food" })
    expect(withinFood(foodRegion, "Emergency")).toHaveTextContent("Fallback")
    expect(screen.getByText("AI service").closest("article")).toHaveTextContent("Needs attention")
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
      return { status: fixture.healthStatus, engine_ready: true, godot_web_ready: true, godot_runtime_ready: true, instance_id: "test", generation: 1 }
    case "/api/v1/admin/runtime/status":
      return {
        status: fixture.runtimeStatus,
        observer: { event_count: 1, last_event: null },
      }
    case "/api/v1/admin/users":
      return { items: [{ presence: "online" }, { presence: "online" }] }
    case "/api/v1/admin/elfies":
      return { items: [adminElfie("00000001"), adminElfie("00000002")] }
    case "/api/v1/admin/runtime/embodiment-sessions":
      return { items: [
        { elfie_id: "00000001", state: "hosted", body_id: "body-1" },
        { elfie_id: "00000002", state: "offline", body_id: null },
      ] }
    case "/api/v1/admin/nest/rooms":
      return { items: [{ beds: fixture.unassignedElfie ? [{ occupant_id: "00000001" }] : [{ occupant_id: "00000001" }, { occupant_id: "00000002" }] }] }
    case "/api/v1/admin/model-providers/connections":
      return { items: [{
        catalog_id: "ollama",
        alias: "Ollama",
        enabled: true,
        archived: false,
        verification: { status: "passed" },
        model_counts: { total: 1, enabled: 1, in_use: fixture.noCoreModel ? 0 : 1, available: 1, degraded: 0, pending: 0, unavailable: 0 },
        models: [{ available: true, hidden: false, retired: false, ...(fixture.noCoreModel ? {} : { verification: { is_core: true } }) }],
      }, ...(fixture.remoteSubscription ? [{
        catalog_id: "volcengine",
        alias: "Volcengine Coding Plan",
        enabled: true,
        archived: false,
        verification: { status: "passed", availability_status: "available" },
        model_counts: { total: 7, enabled: 7, in_use: 0, available: 7, degraded: 0, pending: 0, unavailable: 0 },
        models: Array.from({ length: 7 }, () => ({ available: true, hidden: false, retired: false, verification: { availability_status: "available", is_core: true } })),
      }] : [])] }
    case "/api/v1/admin/model-providers/ollama":
      return {
        state: "healthy",
        recommended_model: "qwen2.5:0.5b",
        installed_model_count: 2,
        model_counts: { installed: 2, available: 1, degraded: 0, pending: 1, unavailable: 0 },
        models: [
          { id: "qwen2.5:0.5b", installed: true, available: true, availability_status: "available" },
          { id: "custom-local:latest", installed: true, available: false, availability_status: "unknown" },
        ],
      }
    case "/api/v1/setup/models":
      return { items: [
        { model_id: "qwen2.5:0.5b", label: "qwen2.5:0.5b", approx_download_mb: 398, recommended: true },
        { model_id: "qwen3.5:0.8b", label: "qwen3.5:0.8b", approx_download_mb: 1024, recommended: false },
      ] }
    case "/api/v1/admin/food-packages":
      return {
        version: 2,
        global_default_food_id: "food_common",
        global_emergency_food_id: "food_emergency",
        packages: fixture.noFoods ? [] : [
          {
            key: "food_common",
            display_name: "Common",
            system_role: "common",
            enabled: true,
            archived: false,
            visibility_mode: "global",
            visible_user_ids: [],
            roles: { primary: fixture.remoteSubscription || fixture.localOnlyCommon ? { model: fixture.localOnlyCommon ? "qwen2.5:0.5b" : "deepseek-v4-flash" } : null, reasoning: null, vision: null, tool: null, fallback: null },
            health: "healthy",
            locality: fixture.localOnlyCommon ? "local" : "remote",
            latest_evidence_at: "2026-08-16T00:00:00Z",
          },
          {
            key: "food_emergency",
            display_name: "Emergency",
            system_role: "emergency",
            enabled: true,
            archived: false,
            visibility_mode: "global",
            visible_user_ids: [],
            roles: { primary: null, reasoning: null, vision: null, tool: null, fallback: null },
            health: fixture.emergencyDegraded ? "degraded" : "healthy",
            locality: "local",
            latest_evidence_at: "2026-08-16T00:00:00Z",
          },
        ],
        eligible_models: [],
      }
    default:
      return { endpoint: "https://raw.example/v1" }
  }
}

function adminElfie(elfieId: string): unknown {
  return {
    owner: { user_id: 1, account_id: "owner", display_name: "Owner" },
    permissions: { can_view_profile: true, can_view_cognition: false },
    profile: {
      elfie_id: elfieId, name: elfieId, species_id: "fox", gender: null,
      birth_date: null, summary: null, adopted_at: "2026-08-01",
      profile_status: "empty", big_five: null, personality_tags: [],
      portrait_url: "", appearance: null,
    },
  }
}

function lastButton(name: string): HTMLElement {
  const buttons = screen.getAllByRole("button", { name })
  const button = buttons.at(-1)
  if (!button) throw new Error(`Missing button: ${name}`)
  return button
}

function withinFood(region: HTMLElement, name: string): HTMLElement {
  const label = Array.from(region.querySelectorAll("strong")).find((item) => item.textContent === name)
  if (!label?.parentElement) throw new Error(`Missing Food: ${name}`)
  return label.parentElement
}
