import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { ObserverCameraCatalog } from "../stores/observer-protocol"
import { useOptionalObserver } from "../stores/observer"
import { ObservationMonitor } from "./ObservationMonitor"

vi.mock("../stores/observer", () => ({
  useOptionalObserver: vi.fn(),
}))

vi.mock("./ObserverSurface", () => ({
  ObserverSurface: ({
    autoStart,
    roomId,
    showHeader,
  }: {
    readonly autoStart?: boolean
    readonly roomId: string
    readonly showHeader?: boolean
  }) => <div data-auto-start={String(autoStart)} data-room-id={roomId} data-show-header={String(showHeader)} data-testid="observer-surface" />,
}))

type ObserverState = NonNullable<ReturnType<typeof useOptionalObserver>>

type ObserverFixture = {
  readonly calls: {
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

describe("ObservationMonitor", () => {
  let fixture: ObserverFixture

  beforeEach(() => {
    vi.clearAllMocks()
    fixture = createObserver(catalog)
    vi.mocked(useOptionalObserver).mockReturnValue(fixture.observer)
  })

  it("keeps reset, overview, generated cameras, pause, and hide in one ordered toolbar", () => {
    render(<ObservationMonitor roomId="local-nest" />)

    const toolbar = screen.getByRole("toolbar", { name: "监控工具栏" })
    expect(within(toolbar).getAllByRole("button").map((button) => button.getAttribute("aria-label"))).toEqual([
      "复位视角",
      "总览",
      "活动区",
      "宿舍区",
      "暂停观察",
      "隐藏工具栏",
    ])
    expect(within(toolbar).getAllByRole("button", { name: "总览" })).toHaveLength(1)
    expect(screen.getByRole("button", { name: "总览" }).querySelector("svg")).toHaveClass("lucide-cctv")
    expect(screen.getAllByRole("toolbar")).toHaveLength(1)
    expect(screen.getByRole("button", { name: "活动区" })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("button", { name: "总览" })).toHaveAttribute("aria-pressed", "false")
    expect(screen.getByTestId("observer-surface")).toHaveAttribute("data-auto-start", "true")
    expect(screen.getByTestId("observer-surface")).toHaveAttribute("data-show-header", "false")
  })

  it("dispatches only high-level view and local-presentation commands", async () => {
    const user = userEvent.setup()
    render(<ObservationMonitor roomId="local-nest" />)

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
    render(<ObservationMonitor roomId="local-nest" />)

    await user.click(screen.getByRole("button", { name: "继续观察" }))

    expect(fixture.calls.setLocalPresentationPaused).toHaveBeenCalledWith(false)
    expect(screen.getByRole("button", { name: "继续观察" })).toBeInTheDocument()
  })

  it("freezes reset, overview, and camera switches while the catalog reports presentation paused", async () => {
    const user = userEvent.setup()
    fixture = createObserver({ ...catalog, presentationPaused: true })
    vi.mocked(useOptionalObserver).mockReturnValue(fixture.observer)
    render(<ObservationMonitor roomId="local-nest" />)

    expect(screen.getByRole("button", { name: "复位视角" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "总览" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "活动区" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "宿舍区" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "继续观察" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "隐藏工具栏" })).toBeEnabled()

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
    render(<ObservationMonitor roomId="local-nest" />)

    const pause = screen.getByRole("button", { name: "暂停观察" })
    expect(pause).toBeEnabled()

    await user.click(pause)

    expect(fixture.calls.setLocalPresentationPaused).toHaveBeenCalledWith(true)
    expect(fixture.calls.detach).not.toHaveBeenCalled()
    expect(fixture.calls.openRoom).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "暂停观察" })).toBeInTheDocument()
  })

  it("removes the complete toolbar until the small restore affordance is used", async () => {
    const user = userEvent.setup()
    render(<ObservationMonitor roomId="local-nest" />)

    await user.click(screen.getByRole("button", { name: "隐藏工具栏" }))

    expect(screen.queryByRole("toolbar", { name: "监控工具栏" })).toBeNull()
    expect(screen.getAllByRole("button").map((button) => button.getAttribute("aria-label"))).toEqual(["显示工具栏"])
    expect(screen.getByRole("button", { name: "显示工具栏" })).toHaveAttribute("title", "显示工具栏")

    await user.click(screen.getByRole("button", { name: "显示工具栏" }))

    expect(screen.getByRole("toolbar", { name: "监控工具栏" })).toBeInTheDocument()
  })
})
