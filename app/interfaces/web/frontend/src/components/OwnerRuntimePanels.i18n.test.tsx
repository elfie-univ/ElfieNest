import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError, ownerRead } from "../api/client"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
import { ManageMonitorPanel } from "./ManageMonitorPanel"
import { ToastProvider } from "./ui/toast"

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return { ...original, ownerRead: vi.fn() }
})

type RuntimeEventFixture = {
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
      if (path === "/api/v1/admin/nest/rooms") return { items: [{ beds: [{ occupant_id: "elfie-1" }, { occupant_id: "elfie-2" }] }] }
      return monitorPayload(path)
    })

    renderWithLocale(<ToastProvider><ManageMonitorPanel /></ToastProvider>, "en-US")

    expect(await screen.findByText("Services healthy")).toBeInTheDocument()
  })

  it("names the unavailable system service in the health card", async () => {
    vi.mocked(ownerRead).mockImplementation(async (path) => {
      if (path === "/api/health") return { status: "ok", engine_ready: true, godot_web_ready: true, godot_runtime_ready: false }
      if (path === "/api/v1/admin/nest/rooms") return { items: [{ beds: [{ occupant_id: "elfie-1" }, { occupant_id: "elfie-2" }] }] }
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
      if (path === "/api/owner/users") throw new ApiError(status, "session expired")
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

function monitorPayload(path: string, lastEvent: RuntimeEventFixture | null = null): unknown {
  switch (path) {
    case "/api/health":
      return { status: "ok", engine_ready: true, godot_web_ready: true, godot_runtime_ready: true }
    case "/api/owner/runtime/status":
      return {
        status: "ok",
        observer: { event_count: lastEvent === null ? 0 : 1, last_event: lastEvent },
      }
    case "/api/owner/users":
      return [{ presence: "online" }, { presence: "offline" }]
    case "/api/owner/elfies":
      return [
        { elfie_id: "elfie-1", profile: { online_status: "online" } },
        { elfie_id: "elfie-2", profile: { online_status: "offline" } },
      ]
    case "/api/v1/admin/nest/rooms":
      return { items: [{ beds: [{ occupant_id: "elfie-1" }, { occupant_id: null }] }] }
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
      return { endpoint: "https://raw.example/v1", protocol_field: "raw_value" }
  }
}
