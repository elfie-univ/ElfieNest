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
  readonly runtimePhase?: "preflight" | "core_starting" | "world_starting"
  readonly godotRuntimeReady?: boolean
  readonly noCoreModel?: boolean
  readonly noFoods?: boolean
  readonly emergencyDegraded?: boolean
  readonly unassignedElfie?: boolean
  readonly remoteSubscription?: boolean
  readonly localOnlyCommon?: boolean
  readonly commonDisabled?: boolean
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

  it("shows Godot startup as pending instead of an error", async () => {
    mockSnapshot({ ...healthyFixture, godotRuntimeReady: false, runtimePhase: "world_starting" })
    renderPanel()

    const health = await screen.findByText("Starting")
    expect(health.closest("article")).toHaveClass("monitor-metric--neutral")
    expect(screen.getByText("(Subservice: Godot runtime starting)")).toBeInTheDocument()
    expect(screen.queryByText("Error")).not.toBeInTheDocument()
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

  it("keeps the AI summary in attention without a remote subscription", async () => {
    api.ownerRead.mockImplementation(async (path: string) => {
      const payload = monitorPayload(path, healthyFixture)
      if (path === "/api/v1/admin/model-providers/ollama") {
        return {
          state: "healthy",
          recommended_model: "qwen2.5:0.5b",
          installed_model_count: 3,
          model_counts: { installed: 3, available: 1, degraded: 0, pending: 2, unavailable: 0 },
          models: [
            { id: "qwen2.5:0.5b", installed: true, available: true, availability_status: "available" },
            { id: "qwen3.5:0.8b", installed: true, available: false, availability_status: "unknown" },
            { id: "gemma3:270m", installed: true, available: false, availability_status: "unknown" },
          ],
        }
      }
      if (path === "/api/v1/setup/models") {
        return { items: [
          { model_id: "qwen2.5:0.5b", label: "qwen2.5:0.5b", approx_download_mb: 398, recommended: true },
          { model_id: "qwen3.5:0.8b", label: "qwen3.5:0.8b", approx_download_mb: 1024, recommended: false },
          { model_id: "gemma3:270m", label: "gemma3:270m", approx_download_mb: 300, recommended: false },
        ] }
      }
      return payload
    })
    renderPanel()

    expect(await screen.findByText("1/3 models available")).toBeInTheDocument()
    expect(screen.getByText("Ollama").closest("li")).toHaveClass("monitor-service--healthy")
    expect(screen.getByText("AI service").closest("article")).toHaveTextContent("Needs attention")
    expect(screen.getByText("AI service").closest("article")).toHaveTextContent("No valid remote model subscription")
  })

  it("keeps the AI summary in attention when Common Food is disabled", async () => {
    mockSnapshot({ ...healthyFixture, commonDisabled: true })
    renderPanel()

    const aiService = await screen.findByText("AI service")
    expect(aiService.closest("article")).toHaveTextContent("Needs attention")
    const foodRegion = screen.getByRole("region", { name: "Food" })
    expect(withinFood(foodRegion, "Common")).toHaveTextContent("Disabled")
    expect(withinFood(foodRegion, "Emergency")).toHaveTextContent("Healthy")
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

  it("shows interstellar travel as enabled when one remote model is available", async () => {
    mockSnapshot({ ...healthyFixture, remoteSubscription: true })
    renderPanel()

    const region = await screen.findByRole("region", { name: "Interstellar travel" })
    await screen.findByText("Enabled")
    expect(region).toHaveTextContent("Enabled")
    expect(region).not.toHaveTextContent("Please provide at least one valid model subscription")
  })

  it("shows interstellar travel before unrelated monitor sources finish", async () => {
    let releaseRuntime: (() => void) | null = null
    const runtimeBlocked = new Promise<void>((resolve) => { releaseRuntime = resolve })
    api.ownerRead.mockImplementation(async (path: string) => {
      if (path === "/api/v1/admin/runtime/status") await runtimeBlocked
      return monitorPayload(path, { ...healthyFixture, remoteSubscription: true })
    })
    renderPanel()

    const region = await screen.findByRole("region", { name: "Interstellar travel" })
    await screen.findByText("Enabled")
    expect(region).toHaveTextContent("Enabled")
    expect(screen.getByText("Loading runtime status...")).toBeInTheDocument()

    await act(async () => { releaseRuntime?.() })
  })

  it("uses the existing unavailable state when the Provider read fails", async () => {
    let providerOptions: unknown
    api.ownerRead.mockImplementation(async (path: string, options?: unknown) => {
      if (path === "/api/v1/admin/model-providers/connections") {
        providerOptions = options
        throw new Error("provider unavailable")
      }
      return monitorPayload(path, healthyFixture)
    })
    renderPanel()

    const region = await screen.findByRole("region", { name: "Interstellar travel" })
    await screen.findByText("Not enabled")
    expect(region).toHaveTextContent("Not enabled")
    expect(providerOptions).toEqual({ timeout: 3000 })
  })

  it("does not require Food or runtime state when a remote model is available", async () => {
    api.ownerRead.mockImplementation(async (path: string) => {
      if (path === "/api/v1/admin/runtime/status") throw new Error("runtime unavailable")
      return monitorPayload(path, { ...healthyFixture, noFoods: true, remoteSubscription: true })
    })
    renderPanel()

    const region = await screen.findByRole("region", { name: "Interstellar travel" })
    await screen.findByText("Enabled")
    expect(region).toHaveTextContent("Enabled")
  })

  it("does not count a local Ollama model as a valid interstellar subscription", async () => {
    mockSnapshot({ ...healthyFixture, localOnlyCommon: true })
    renderPanel()

    const region = await screen.findByRole("region", { name: "Interstellar travel" })
    await screen.findByText("Not enabled")
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
      return { status: fixture.healthStatus, engine_ready: true, godot_web_ready: true, godot_runtime_ready: fixture.godotRuntimeReady ?? true, instance_id: "test", generation: 1 }
    case "/api/v1/admin/runtime/status":
      return {
        status: fixture.runtimeStatus,
        observer: { event_count: 1, last_event: null },
        ...(fixture.runtimePhase === undefined ? {} : { lifecycle: lifecyclePayload(fixture.runtimePhase) }),
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
            enabled: !fixture.commonDisabled,
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

function lifecyclePayload(phase: NonNullable<MonitorFixture["runtimePhase"]>): unknown {
  return {
    schema_version: 1,
    instance_id: "test",
    generation: 1,
    revision: 1,
    tier: "core_ready",
    phase,
    subphase: "authority_starting",
    desired_target: "normal",
    reached_target: "core",
    components: [{ component: "godot_authority", state: "starting", detail: "", pid: null, executable: null, birth_identity: null }],
    endpoints: [],
    model_state: "ready",
    model_common_state: "ready",
    model_emergency_state: "ready",
    model_revision: 1,
    failures: [],
    timings: [],
    protocol_versions: [],
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
