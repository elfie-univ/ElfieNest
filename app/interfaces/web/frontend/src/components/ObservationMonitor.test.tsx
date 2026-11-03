import { render, screen, within, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { i18n } from "i18next"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { elfies, type ElfieProfile } from "../api/elfies/profiles"
import { adminElfies } from "../api/admin/elfies"
import { createI18n } from "../i18n/config"
import { localizeBackendDetail } from "../i18n/errors"
import type { SupportedLocale } from "../i18n/locale"
import type { ObserverCameraCatalog } from "../stores/observer-protocol"
import { useOptionalObserver } from "../stores/observer"
import { monitorStatusKey, ObservationMonitor } from "./ObservationMonitor"

vi.mock("../api/elfies/profiles", () => ({ elfies: vi.fn() }))
vi.mock("../api/admin/elfies", () => ({ adminElfies: vi.fn() }))

vi.mock("../stores/observer", () => ({
  useOptionalObserver: vi.fn(),
}))

vi.mock("./ObserverSurface", () => ({
  ObserverSurface: ({
    autoStart,
    roomId,
    showHeader,
    title,
  }: {
    readonly autoStart?: boolean
    readonly roomId: string
    readonly showHeader?: boolean
    readonly title: string
  }) => <div aria-label={title} data-auto-start={String(autoStart)} data-room-id={roomId} data-show-header={String(showHeader)} data-testid="observer-surface" role="region" />,
}))

type ObserverState = NonNullable<ReturnType<typeof useOptionalObserver>>

type ObserverFixture = {
  readonly calls: {
    readonly configureRoom: ReturnType<typeof vi.fn>
    readonly detach: ReturnType<typeof vi.fn>
    readonly openRoom: ReturnType<typeof vi.fn>
    readonly overview: ReturnType<typeof vi.fn>
    readonly reset: ReturnType<typeof vi.fn>
    readonly select: ReturnType<typeof vi.fn>
    readonly setLocalPresentationPaused: ReturnType<typeof vi.fn>
  }
  readonly observer: ObserverState
}

const catalog = {
  activeId: "overview",
  presentationPaused: false, revision: 1,
  views: [
    { id: "overview", label: "全园总览" }, { id: "estate-ring", label: "环形路" },
    ...Array.from({ length: 4 }, (_, i) => ({ id: `central-${i + 1}`, label: `主楼 · ${i + 1} 层` })),
    ...Array.from({ length: 8 }, (_, i) => [
      { id: `dorm-0${i + 1}`, label: `卧室 M0${i + 1} · 一层` },
      { id: `terrace-0${i + 1}`, label: `卧室 M0${i + 1} · 二层` },
    ]).flat(),
    { id: "lighting-live", label: "Live" }, { id: "lighting-day", label: "Day" },
    { id: "lighting-night", label: "Night" }, { id: "lighting-quiet", label: "Quiet" },
    { id: "access-estate", label: "Inspection" },
    { id: "elfie-00000001", label: "Follow one" }, { id: "elfie-pov-00000001", label: "POV one" },
    { id: "elfie-00000002", label: "Other owner" },
  ],
} satisfies ObserverCameraCatalog

const owned: ElfieProfile = {
  elfie_id: "00000001", name: "Mochi", species_id: "saevi", gender: null,
  birth_date: null, summary: null, adopted_at: "2026-08-01", profile_status: "empty",
  big_five: null, personality_tags: [], portrait_url: "", appearance: null, relationship: "owned",
}

function createObserver(
  cameraCatalog: ObserverCameraCatalog | null,
  status: ObserverState["status"] = "ready",
  entityCount = 0,
): ObserverFixture {
  const calls = {
    configureRoom: vi.fn(),
    detach: vi.fn(),
    openRoom: vi.fn(async () => undefined),
    overview: vi.fn(),
    reset: vi.fn(),
    select: vi.fn(),
    setLocalPresentationPaused: vi.fn(),
  }
  return {
    calls,
    observer: {
    attach: vi.fn(),
    cameraCatalog,
    configureRoom: calls.configureRoom,
      detach: calls.detach,
      entities: Object.fromEntries(
        Array.from({ length: entityCount }, (_, index) => [`elfie-${index + 1}`, {}]),
      ) as ObserverState["entities"],
      fallbackReason: null,
      openElfie: vi.fn(async () => undefined),
      openRoom: calls.openRoom,
      overview: calls.overview,
      reset: calls.reset,
      select: calls.select,
      setLocalPresentationPaused: calls.setLocalPresentationPaused,
      status,
    },
  }
}

function renderMonitor(
  locale: SupportedLocale = "zh-CN",
  mode: "embedded" | "standalone" = "embedded",
  immersive = false,
  onExitImmersive = vi.fn(),
  elfieScope: "owned" | "all" = "owned",
): i18n {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  render(<I18nextProvider i18n={instance}><ObservationMonitor elfieScope={elfieScope} immersive={immersive} mode={mode} onExitImmersive={onExitImmersive} roomId="local-nest" /></I18nextProvider>)
  return instance
}

describe("ObservationMonitor", () => {
  let fixture: ObserverFixture
  beforeEach(() => {
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
    vi.clearAllMocks()
    vi.mocked(elfies).mockResolvedValue([])
    vi.mocked(adminElfies).mockResolvedValue([])
    fixture = createObserver(catalog)
    vi.mocked(useOptionalObserver).mockReturnValue(fixture.observer)
  })

  it("shows the mode buttons, fixed view selector and reset in that order", () => {
    renderMonitor()
    expect(screen.queryByRole("button", { name: "总览" })).not.toBeInTheDocument()
    expect(screen.queryByRole("combobox", { name: "操作方式" })).not.toBeInTheDocument()
    const left = screen.getByRole("group", { name: "视角操作" })
    const right = screen.getByRole("group", { name: "时间与播放" })
    expect(left.children).toHaveLength(3)
    expect(screen.queryByRole("combobox", { name: "视角类型" })).not.toBeInTheDocument()
    expect(screen.queryByText("视角类型")).not.toBeInTheDocument()
    expect(within(left).getAllByRole("combobox").map((item) => item.textContent)).toEqual(["全园总览"])
    expect(within(screen.getByRole("group", { name: "视角切换" })).getAllByRole("button").map((item) => item.textContent)).toEqual(["固定机位", "精灵视角"])
    expect(screen.getByRole("button", { name: "固定机位" })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("button", { name: "精灵视角" })).toHaveAttribute("aria-pressed", "false")
    expect(left.lastElementChild).toBe(screen.getByRole("button", { name: "复位视角" }))
    expect(screen.queryByRole("combobox", { name: "时间" })).not.toBeInTheDocument()
    expect(right).toContainElement(screen.getByRole("button", { name: "暂停观察" }))
    expect(screen.queryByRole("separator")).not.toBeInTheDocument()
    expect(screen.getAllByRole("toolbar")).toHaveLength(1)
  })

  it.each(["", "0", "true", "1"])("keeps lighting preview in Developer Tools for debug=%s", (value) => {
    window.history.replaceState(null, "", `/monitor?debug=${value}`)
    renderMonitor()
    expect(screen.queryByRole("combobox", { name: "时间" })).not.toBeInTheDocument()
    expect(fixture.calls.select).not.toHaveBeenCalled()
  })

  it("keeps the product monitor focused on observation with debug=1", () => {
    window.history.replaceState(null, "", "/monitor?room=local-nest&debug=1")
    renderMonitor()
    expect(screen.queryByRole("combobox", { name: "时间" })).not.toBeInTheDocument()
    expect(screen.queryByRole("separator")).not.toBeInTheDocument()
    expect(fixture.calls.select).not.toHaveBeenCalled()
  })

  it("labels the authorized resident count without claiming rendered visibility", () => {
    fixture = createObserver(catalog, "ready", 3)
    vi.mocked(useOptionalObserver).mockReturnValue(fixture.observer)
    renderMonitor()
    expect(screen.getByText("观察范围内有 3 位精灵。")).toBeInTheDocument()
    expect(screen.queryByText("当前可见 3 位精灵。")).not.toBeInTheDocument()
  })

  it("groups all 22 fixed cameras into courtyard, main building and bedrooms", async () => {
    const user = userEvent.setup()
    renderMonitor()
    await user.click(screen.getByRole("combobox", { name: "视角" }))
    const list = screen.getByRole("listbox")
    expect(within(list).getAllByRole("option")).toHaveLength(22)
    expect(within(list).getByText("庭院")).toBeInTheDocument()
    expect(within(list).getByText("主楼")).toBeInTheDocument()
    expect(within(list).getByText("卧室")).toBeInTheDocument()
    expect(within(list).queryByText("露台")).not.toBeInTheDocument()
    const labels = within(list).getAllByRole("option").map((item) => item.textContent)
    expect(labels.slice(6, 10)).toEqual(["卧室 M01 · 一层", "卧室 M01 · 二层", "卧室 M02 · 一层", "卧室 M02 · 二层"])
    expect(within(list).queryByText("Other owner")).not.toBeInTheDocument()
    expect(within(list).queryByText("Inspection")).not.toBeInTheDocument()
    const bedroomColors = ["#95b58c", "#d39bae", "#91bbd7", "#d5a078", "#83bbb5", "#b8a2ce", "#d8cc92", "#8791bc"]
    for (const [index, color] of bedroomColors.entries()) {
      const room = `M0${index + 1}`
      for (const floor of ["一层", "二层"]) {
        const option = within(list).getByRole("option", { name: `卧室 ${room} · ${floor}` })
        expect(option.querySelector('[data-slot="select-marker"]')).toHaveStyle({ backgroundColor: color })
      }
    }
    expect(within(list).getByRole("option", { name: "全园总览" }).querySelector('[data-slot="select-marker"]')).toBeNull()
    await user.click(screen.getByRole("option", { name: "主楼 · 2 层" }))
    expect(fixture.calls.select).toHaveBeenLastCalledWith("central-2")
  })

  it("keeps the bedroom marker beside the selected view without changing its label", () => {
    fixture = createObserver({ ...catalog, activeId: "terrace-08" })
    vi.mocked(useOptionalObserver).mockReturnValue(fixture.observer)
    renderMonitor()
    const view = screen.getByRole("combobox", { name: "视角" })
    expect(view).toHaveTextContent("卧室 M08 · 二层")
    expect(view.querySelector('[data-slot="select-marker"]')).toHaveStyle({ backgroundColor: "#8791bc" })
  })

  it("resets the current fixed camera without selecting another camera or changing modes", async () => {
    fixture = createObserver({ ...catalog, activeId: "central-2" })
    vi.mocked(useOptionalObserver).mockReturnValue(fixture.observer)
    renderMonitor()
    await userEvent.click(screen.getByRole("button", { name: "固定机位" }))
    await userEvent.click(screen.getByRole("button", { name: "复位视角" }))
    expect(fixture.calls.reset).toHaveBeenCalledOnce()
    expect(fixture.calls.select).not.toHaveBeenCalled()
    expect(screen.getByRole("combobox", { name: "视角" })).toHaveTextContent("主楼 · 2 层")
  })

  it("requests owned Elfies, excludes others and switches follow/first-person on the same resident", async () => {
    vi.mocked(elfies).mockResolvedValue([owned, { ...owned, elfie_id: "00000002", name: "Other", relationship: "other" }, { ...owned, elfie_id: "00000003", name: "Offline" }])
    const user = userEvent.setup()
    renderMonitor()
    await waitFor(() => expect(elfies).toHaveBeenCalledWith("owned"))
    expect(adminElfies).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: "精灵视角" }))
    expect(fixture.calls.select).toHaveBeenLastCalledWith("elfie-00000001")
    expect(screen.queryByRole("combobox", { name: "操作方式" })).not.toBeInTheDocument()
    expect(screen.getByRole("group", { name: "视角操作" }).children).toHaveLength(3)
    expect(within(screen.getByRole("group", { name: "视角操作" })).getAllByRole("combobox").map((item) => item.textContent)).toEqual(["Mochi", "跟随"])
    expect(screen.queryByRole("button", { name: "复位视角" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "精灵视角" })).toHaveAttribute("aria-pressed", "true")
    expect(fixture.calls.select).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole("combobox", { name: "精灵" }))
    expect(screen.queryByRole("option", { name: "Other" })).not.toBeInTheDocument()
    expect(screen.getByRole("option", { name: "Offline · 不在场景" })).toHaveAttribute("aria-disabled", "true")
    await user.keyboard("{Escape}")
    await user.click(screen.getByRole("combobox", { name: "观看方式" }))
    await user.click(screen.getByRole("option", { name: "代入" }))
    expect(fixture.calls.select).toHaveBeenLastCalledWith("elfie-pov-00000001")
    expect(screen.queryByRole("button", { name: "复位视角" })).not.toBeInTheDocument()
    expect(fixture.calls.reset).not.toHaveBeenCalled()
    expect(fixture.calls.select).toHaveBeenCalledTimes(2)
    await user.click(screen.getByRole("button", { name: "固定机位" }))
    expect(fixture.calls.select).toHaveBeenLastCalledWith("overview")
    expect(screen.getByRole("button", { name: "复位视角" })).toBeEnabled()
    expect(screen.queryByRole("combobox", { name: "观看方式" })).not.toBeInTheDocument()
  })

  it("uses the protected admin directory and permits another owner's resident in manager scope", async () => {
    vi.mocked(adminElfies).mockResolvedValue([
      { owner: { user_id: 2, account_id: "other-owner", display_name: null }, permissions: { can_view_profile: true, can_view_cognition: false }, profile: { ...owned, elfie_id: "00000002", name: "Other" } },
    ])
    const user = userEvent.setup()
    renderMonitor("zh-CN", "embedded", false, vi.fn(), "all")
    await waitFor(() => expect(adminElfies).toHaveBeenCalledOnce())
    expect(elfies).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: "精灵视角" }))
    expect(screen.getByRole("combobox", { name: "精灵" })).toHaveTextContent("Other")
    expect(screen.queryByText("我的精灵")).not.toBeInTheDocument()
    expect(fixture.calls.select).toHaveBeenLastCalledWith("elfie-00000002")
  })

  it("shows a disabled empty owned selection without choosing someone else's camera", async () => {
    const user = userEvent.setup()
    renderMonitor()
    await user.click(screen.getByRole("button", { name: "精灵视角" }))
    expect(screen.getByRole("combobox", { name: "精灵" })).toBeDisabled()
    expect(screen.getByRole("combobox", { name: "精灵" })).toHaveTextContent("暂无可观察的精灵")
    expect(screen.queryByRole("button", { name: "复位视角" })).not.toBeInTheDocument()
    expect(fixture.calls.select).not.toHaveBeenCalled()
  })

  it("keeps the loading failure distinct from an empty owned list", async () => {
    vi.mocked(elfies).mockRejectedValue(new Error("unavailable"))
    const user = userEvent.setup()
    renderMonitor()
    await user.click(screen.getByRole("button", { name: "精灵视角" }))
    expect(screen.getByRole("combobox", { name: "精灵" })).toHaveTextContent("精灵列表加载失败")
    expect(fixture.calls.select).not.toHaveBeenCalled()
  })

  it("pauses through the presentation bridge without a lighting override", async () => {
    window.history.replaceState(null, "", "/monitor?debug=1")
    const user = userEvent.setup()
    renderMonitor()
    expect(screen.queryByRole("combobox", { name: "时间" })).not.toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: "视角" })).toHaveTextContent("全园总览")
    await user.click(screen.getByRole("button", { name: "暂停观察" }))
    expect(fixture.calls.setLocalPresentationPaused).toHaveBeenCalledWith(true)
    expect(fixture.calls.detach).not.toHaveBeenCalled()
  })

  it("disables all view changes while paused and keeps resume enabled", async () => {
    fixture = createObserver({ ...catalog, presentationPaused: true })
    vi.mocked(useOptionalObserver).mockReturnValue(fixture.observer)
    renderMonitor()
    for (const control of screen.getAllByRole("combobox")) expect(control).toBeDisabled()
    expect(screen.getByRole("button", { name: "复位视角" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "固定机位" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "精灵视角" })).toBeDisabled()
    await userEvent.click(screen.getByRole("button", { name: "继续观察" }))
    expect(fixture.calls.setLocalPresentationPaused).toHaveBeenCalledWith(false)
    expect(fixture.calls.select).not.toHaveBeenCalled()
  })

  it("disables controls until connected and exposes a safe offline status", () => {
    vi.mocked(useOptionalObserver).mockReturnValue(null)
    renderMonitor("en-US")
    for (const control of screen.getAllByRole("combobox")) expect(control).toBeDisabled()
    expect(screen.getByRole("button", { name: "Pause monitoring" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Reset view" })).toBeDisabled()
    expect(screen.getByRole("status")).toHaveTextContent("Monitoring is unavailable.")
    expect(monitorStatusKey("foreign")).toBe("status.unknown")
  })

  it("localizes controls without rewriting runtime view labels", () => {
    renderMonitor("en-US")
    expect(screen.getByRole("button", { name: "Fixed cameras" })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("button", { name: "Elfie view" })).toHaveAttribute("aria-pressed", "false")
    expect(screen.getByRole("combobox", { name: "View" })).toHaveTextContent("全园总览")
    expect(screen.queryByRole("combobox", { name: "Operation mode" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Reset view" })).toHaveTextContent("Reset")
    expect(screen.getByRole("status")).toHaveTextContent("Connected to local-nest")
  })

  it("keeps immersive exit and runtime retry behavior", async () => {
    fixture = createObserver(null, "fallback")
    vi.mocked(useOptionalObserver).mockReturnValue({ ...fixture.observer, fallbackReason: "runtime" })
    renderMonitor("en-US", "standalone", true)
    expect(screen.getByRole("button", { name: "Exit immersive monitoring" })).toBeInTheDocument()
    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Retry 3D monitoring" }))
    expect(fixture.calls.openRoom).toHaveBeenCalledWith("local-nest", expect.objectContaining({ nest_id: "local-nest" }))
    expect(localizeBackendDetail("secret", "monitor.connect", "en-US")).not.toContain("secret")
  })
})
