import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError, ownerRead } from "../api/http"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
import { ManageMonitorPanel } from "./ManageMonitorPanel"
import { ToastProvider } from "./ui/toast"

vi.mock("../api/http", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/http")>()
  const read = vi.fn()
  return { ...original, ownerRead: read, requestJson: read }
})

type ModelExecutionEventFixture = {
  readonly event_type: string
  readonly status: string
  readonly subject: string
  readonly metadata: Record<string, unknown>
}

describe("runtime panel behavior", () => {
  beforeEach(() => {
    vi.mocked(ownerRead).mockImplementation(async (path) => monitorPayload(path))
  })

  it("renders the monitor in English while preserving technical values", async () => {
    renderWithLocale(<ToastProvider><ManageMonitorPanel /></ToastProvider>, "en-US")

    expect(await screen.findByText("Model service details")).toBeInTheDocument()
    expect(screen.getByText("Users")).toBeInTheDocument()
    expect(screen.getByText("Elfies")).toBeInTheDocument()
    expect(screen.getByText("Ollama")).toBeInTheDocument()
    expect(screen.getAllByText("Needs attention")).not.toHaveLength(0)
    expect(screen.getByText("1 Elfies have no assigned bed")).toBeInTheDocument()
  })

  it("shows a concise healthy status when no issue is present", async () => {
    vi.mocked(ownerRead).mockImplementation(async (path) => {
      if (path === "/api/v1/admin/nest/rooms") return { items: [{ beds: [{ occupant_id: "00000001" }, { occupant_id: "00000002" }] }] }
      return monitorPayload(path)
    })

    renderWithLocale(<ToastProvider><ManageMonitorPanel /></ToastProvider>, "en-US")

    expect(await screen.findByText("Services healthy")).toBeInTheDocument()
  })

  it("names the unavailable system service in the health card", async () => {
    vi.mocked(ownerRead).mockImplementation(async (path) => {
      if (path === "/api/health") return { status: "ok", engine_ready: true, godot_web_ready: true, godot_runtime_ready: false }
      if (path === "/api/v1/admin/nest/rooms") return { items: [{ beds: [{ occupant_id: "00000001" }, { occupant_id: "00000002" }] }] }
      return monitorPayload(path)
    })

    renderWithLocale(<ToastProvider><ManageMonitorPanel /></ToastProvider>, "zh-CN")

    expect(await screen.findByText("（子服务：Godot 运行时异常）")).toBeInTheDocument()
    expect(screen.getByText("Godot 运行时异常")).toBeInTheDocument()
  })

  it("renders a structured latest runtime event without treating it as a load failure", async () => {
    vi.mocked(ownerRead).mockImplementation(async (path) => monitorPayload(path, {
      event_type: "fallback",
      status: "ok",
      subject: "local_fast",
      metadata: {},
    }))

    renderWithLocale(<ToastProvider><ManageMonitorPanel /></ToastProvider>, "zh-CN")

    expect(await screen.findByText(/local_fast/)).toBeInTheDocument()
    expect(screen.queryByText("管理数据加载失败。")).not.toBeInTheDocument()
  })

  it("keeps the available cards visible when one read-only source fails", async () => {
    vi.mocked(ownerRead).mockImplementation(async (path) => {
      if (path === "/api/v1/admin/nest/rooms") throw new Error("rooms unavailable")
      return monitorPayload(path)
    })

    renderWithLocale(<ToastProvider><ManageMonitorPanel /></ToastProvider>, "zh-CN")

    expect(await screen.findByText("部分状态数据暂时无法读取。")).toBeInTheDocument()
    expect(screen.getByText("用户")).toBeInTheDocument()
    expect(screen.getAllByText("2")).toHaveLength(2)
    expect(screen.getByText("模型服务明细")).toBeInTheDocument()
  })

  it.each([401, 403])("shows an authentication notice for protected read status %i", async (status) => {
    vi.mocked(ownerRead).mockImplementation(async (path) => {
      if (path === "/api/v1/admin/users") throw new ApiError(status, "session expired")
      return monitorPayload(path)
    })

    renderWithLocale(<ToastProvider><ManageMonitorPanel /></ToastProvider>, "zh-CN")

    expect(await screen.findByText("管理会话已失效，请重新登录。")).toBeInTheDocument()
    expect(screen.queryByText("部分状态数据暂时无法读取。")).not.toBeInTheDocument()
  })

})

function renderWithLocale(node: React.ReactNode, locale: SupportedLocale): ReturnType<typeof createI18n> {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  document.documentElement.lang = locale
  render(<I18nextProvider i18n={instance}>{node}</I18nextProvider>)
  return instance
}

function monitorPayload(path: string, lastEvent: ModelExecutionEventFixture | null = null): unknown {
  switch (path) {
    case "/api/health":
      return { status: "ok", engine_ready: true, godot_web_ready: true, godot_runtime_ready: true }
    case "/api/v1/admin/runtime/status":
      return {
        status: "ok",
        observer: { event_count: lastEvent === null ? 0 : 1, last_event: lastEvent },
      }
    case "/api/v1/admin/users":
      return { items: [{ presence: "online" }, { presence: "offline" }] }
    case "/api/v1/admin/elfies":
      return { items: [adminElfie("00000001"), adminElfie("00000002")] }
    case "/api/v1/admin/runtime/embodiment-sessions":
      return { items: [
        { elfie_id: "00000001", state: "hosted", body_id: "body-1" },
        { elfie_id: "00000002", state: "offline", body_id: null },
      ] }
    case "/api/v1/admin/nest/rooms":
      return { items: [{ beds: [{ occupant_id: "00000001" }, { occupant_id: null }] }] }
    case "/api/v1/admin/model-providers/connections":
      return { items: [{
        catalog_id: "ollama",
        alias: "Ollama",
        enabled: true,
        archived: false,
        verification: { status: "passed" },
        models: [{ available: true, hidden: false, retired: false }],
      }] }
    case "/api/v1/admin/model-providers/ollama":
      return { state: "healthy", recommended_model: "qwen2.5:0.5b", installed_model_count: 1 }
    default:
      return { endpoint: "https://raw.example/v1", protocol_field: "raw_value" }
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
