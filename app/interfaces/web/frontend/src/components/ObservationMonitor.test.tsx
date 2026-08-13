import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { i18n } from "i18next"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { createI18n } from "../i18n/config"
import { localizeBackendDetail } from "../i18n/errors"
import type { SupportedLocale } from "../i18n/locale"
import type { ObserverCameraCatalog } from "../stores/observer-protocol"
import { useOptionalObserver } from "../stores/observer"
import { monitorStatusKey, ObservationMonitor } from "./ObservationMonitor"

vi.mock("../stores/observer", () => ({
  useOptionalObserver: vi.fn(),
}))

vi.mock("./ObserverSurface", () => ({
  ObserverSurface: ({
    autoStart,
    bedCount,
    roomId,
    showHeader,
    title,
  }: {
    readonly autoStart?: boolean
    readonly bedCount: number
    readonly roomId: string
    readonly showHeader?: boolean
    readonly title: string
  }) => <div aria-label={title} data-auto-start={String(autoStart)} data-bed-count={String(bedCount)} data-room-id={roomId} data-show-header={String(showHeader)} data-testid="observer-surface" role="region" />,
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
  activeId: "activity-01",
  presentationPaused: false,
  revision: 1,
  views: [
    { id: "overview", label: "总览" },
    { id: "activity-01", label: "活动区" },
    { id: "dorm-01", label: "宿舍区" },
  ],
} satisfies ObserverCameraCatalog

function createObserver(cameraCatalog: ObserverCameraCatalog | null): ObserverFixture {
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
      entities: {},
      fallbackReason: null,
      openElfie: vi.fn(async () => undefined),
      openRoom: calls.openRoom,
      overview: calls.overview,
      reset: calls.reset,
      select: calls.select,
      setLocalPresentationPaused: calls.setLocalPresentationPaused,
      status: "ready",
    },
  }
}

function renderMonitor(
  locale: SupportedLocale = "zh-CN",
  bedCount = 4,
  mode: "embedded" | "standalone" = "embedded",
  immersive = false,
  onExitImmersive = vi.fn(),
): i18n {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  render(<I18nextProvider i18n={instance}><ObservationMonitor bedCount={bedCount} immersive={immersive} mode={mode} onExitImmersive={onExitImmersive} roomId="local-nest" /></I18nextProvider>)
  return instance
}

describe("ObservationMonitor", () => {
  let fixture: ObserverFixture

  beforeEach(() => {
    vi.clearAllMocks()
    fixture = createObserver(catalog)
    vi.mocked(useOptionalObserver).mockReturnValue(fixture.observer)
  })

  it("keeps reset, overview, generated cameras, and pause in one ordered toolbar", () => {
    renderMonitor()

    const toolbar = screen.getByRole("toolbar", { name: "监控工具栏" })
    expect(within(toolbar).getAllByRole("button").map((button) => button.getAttribute("aria-label"))).toEqual([
      "复位视角",
      "总览",
      "活动区",
      "宿舍区",
      "暂停观察",
    ])
    expect(within(toolbar).getAllByRole("button", { name: "总览" })).toHaveLength(1)
    expect(screen.getByRole("button", { name: "总览" }).querySelector("svg")).toHaveClass("lucide-cctv")
    expect(screen.getAllByRole("toolbar")).toHaveLength(1)
    expect(screen.getByRole("button", { name: "活动区" })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("button", { name: "总览" })).toHaveAttribute("aria-pressed", "false")
    expect(screen.getByTestId("observer-surface")).toHaveAttribute("data-auto-start", "true")
    expect(screen.getByTestId("observer-surface")).toHaveAttribute("data-bed-count", "4")
    expect(screen.getByTestId("observer-surface")).toHaveAttribute("data-show-header", "false")
  })

  it("keeps the embedded preview free of standalone navigation controls", () => {
    renderMonitor()

    expect(screen.queryByRole("link", { name: "返回管理" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "进入沉浸观察" })).not.toBeInTheDocument()
    expect(screen.getByRole("toolbar", { name: "监控工具栏" })).toBeInTheDocument()
  })

  it("hides standalone navigation and the camera toolbar in immersive mode", async () => {
    const user = userEvent.setup()
    const onExitImmersive = vi.fn()
    renderMonitor("zh-CN", 4, "standalone", true, onExitImmersive)

    expect(screen.queryByRole("toolbar", { name: "监控工具栏" })).toBeNull()
    await user.click(screen.getByRole("button", { name: "退出沉浸观察" }))

    expect(onExitImmersive).toHaveBeenCalledOnce()
  })

  it("dispatches only high-level view and local-presentation commands", async () => {
    const user = userEvent.setup()
    renderMonitor()

    await user.click(screen.getByRole("button", { name: "复位视角" }))
    await user.click(screen.getByRole("button", { name: "总览" }))
    await user.click(screen.getByRole("button", { name: "宿舍区" }))
    await user.click(screen.getByRole("button", { name: "暂停观察" }))

    expect(fixture.calls.reset).toHaveBeenCalledOnce()
    expect(fixture.calls.overview).toHaveBeenCalledOnce()
    expect(fixture.calls.select).toHaveBeenCalledWith("dorm-01")
    expect(fixture.calls.setLocalPresentationPaused).toHaveBeenCalledWith(true)
    expect(fixture.calls.detach).not.toHaveBeenCalled()
    expect(fixture.calls.openRoom).not.toHaveBeenCalled()
  })

  it("uses the current catalog pause state without changing it optimistically", async () => {
    const user = userEvent.setup()
    fixture = createObserver({ ...catalog, presentationPaused: true })
    vi.mocked(useOptionalObserver).mockReturnValue(fixture.observer)
    renderMonitor()

    await user.click(screen.getByRole("button", { name: "继续观察" }))

    expect(fixture.calls.setLocalPresentationPaused).toHaveBeenCalledWith(false)
    expect(screen.getByRole("button", { name: "继续观察" })).toBeInTheDocument()
  })

  it("freezes reset, overview, and camera switches while the catalog reports presentation paused", async () => {
    const user = userEvent.setup()
    fixture = createObserver({ ...catalog, presentationPaused: true })
    vi.mocked(useOptionalObserver).mockReturnValue(fixture.observer)
    renderMonitor()

    expect(screen.getByRole("button", { name: "复位视角" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "总览" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "活动区" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "宿舍区" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "继续观察" })).toBeEnabled()

    await user.click(screen.getByRole("button", { name: "复位视角" }))
    await user.click(screen.getByRole("button", { name: "总览" }))
    await user.click(screen.getByRole("button", { name: "活动区" }))
    await user.click(screen.getByRole("button", { name: "继续观察" }))

    expect(fixture.calls.reset).not.toHaveBeenCalled()
    expect(fixture.calls.overview).not.toHaveBeenCalled()
    expect(fixture.calls.select).not.toHaveBeenCalled()
    expect(fixture.calls.setLocalPresentationPaused).toHaveBeenCalledWith(false)
    expect(fixture.calls.detach).not.toHaveBeenCalled()
    expect(fixture.calls.openRoom).not.toHaveBeenCalled()
  })

  it("keeps local pause available before the camera catalog arrives without reopening the observer", async () => {
    const user = userEvent.setup()
    fixture = createObserver(null)
    vi.mocked(useOptionalObserver).mockReturnValue(fixture.observer)
    renderMonitor()

    const pause = screen.getByRole("button", { name: "暂停观察" })
    expect(pause).toBeEnabled()

    await user.click(pause)

    expect(fixture.calls.setLocalPresentationPaused).toHaveBeenCalledWith(true)
    expect(fixture.calls.detach).not.toHaveBeenCalled()
    expect(fixture.calls.openRoom).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "暂停观察" })).toBeInTheDocument()
  })

  it("renders English controls and connection status while preserving runtime camera data", () => {
    // Given: a ready observer publishes runtime-owned camera labels and IDs.
    renderMonitor("en-US")

    // When: the English monitor toolbar is inspected.
    const toolbar = screen.getByRole("toolbar", { name: "Monitoring controls" })

    // Then: UI-owned controls are English while runtime labels remain byte-for-byte unchanged.
    expect(within(toolbar).getAllByRole("button").map((button) => button.getAttribute("aria-label"))).toEqual([
      "Reset view",
      "Overview",
      "活动区",
      "宿舍区",
      "Pause monitoring",
    ])
    expect(screen.getByRole("status")).toHaveTextContent("Connected to local-nest")
    expect(screen.getByRole("region", { name: "3D room monitor" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "活动区" })).toHaveAttribute("aria-pressed", "true")
  })

  it("localizes the immersive exit control", async () => {
    const instance = renderMonitor("zh-CN", 4, "standalone", true)

    expect(screen.getByRole("button", { name: "退出沉浸观察" })).toBeInTheDocument()
    await instance.changeLanguage("en-US")

    expect(screen.getByRole("button", { name: "Exit immersive monitoring" })).toBeInTheDocument()
  })

  it("reports offline and unknown monitor states with localized safe copy", () => {
    // Given: the observer context is offline and a foreign status value is probed.
    vi.mocked(useOptionalObserver).mockReturnValue(null)

    // When: the English monitor renders and the closed status mapper sees an unknown value.
    renderMonitor("en-US")
    const unknownKey = monitorStatusKey("stale-external-status")

    // Then: controls are disabled and neither state exposes raw external data.
    expect(screen.getByRole("status")).toHaveTextContent("Monitoring is unavailable.")
    expect(screen.getByRole("button", { name: "Reset view" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Pause monitoring" })).toBeDisabled()
    expect(unknownKey).toBe("status.unknown")
  })

  it("keeps long English controls in the single horizontally scrollable toolbar", () => {
    // Given: the English locale uses its longest control labels.
    renderMonitor("en-US")

    // When: the control surface is inspected as one toolbar.
    const toolbar = screen.getByRole("toolbar", { name: "Monitoring controls" })

    // Then: every label remains inside the existing overflow container.
    expect(toolbar).toHaveClass("observation-monitor__toolbar")
    expect(within(toolbar).getByRole("button", { name: "Pause monitoring" })).toHaveTextContent("Pause monitoring")
    expect(screen.getAllByRole("toolbar")).toHaveLength(1)
  })

  it("hides backend detail from English monitor errors", () => {
    // Given: an observer failure includes misleading raw backend payload text.
    const detail = "连接失败: capability=secret-token payload={raw:true}"

    // When: the established localized monitor error boundary formats it for English.
    const message = localizeBackendDetail(detail, "monitor.connect", "en-US")

    // Then: only the local fallback is exposed.
    expect(message).toBe("Unable to connect to monitoring.")
    expect(message).not.toContain(detail)
  })

  it("replaces a stale runtime fallback with localized help and a high-level retry", async () => {
    // Given: the Observer reports a stale runtime readiness failure.
    const user = userEvent.setup()
    fixture = createObserver(null)
    vi.mocked(useOptionalObserver).mockReturnValue({
      ...fixture.observer,
      fallbackReason: "runtime",
      status: "fallback",
    })

    // When: the English fallback is rendered and retried.
    renderMonitor("en-US")
    await user.click(screen.getByRole("button", { name: "Retry 3D monitoring" }))

    // Then: safe local help replaces runtime detail and only the existing room action runs.
    expect(screen.getByText("The local 3D runtime stopped responding. You can retry without leaving this page.")).toBeInTheDocument()
    expect(fixture.calls.openRoom).toHaveBeenCalledWith("local-nest", {
      channel: "elfienest.observer",
      version: 1,
      kind: "world_config",
      nest_id: "local-nest",
      bed_count: 4,
    })
    expect(fixture.calls.detach).not.toHaveBeenCalled()
  })
})
