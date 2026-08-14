import { act, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { openObserverSession } from "../api/observer"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
import { isObserverContextAllowed, ObserverProvider } from "../stores/observer"
import { ObserverSurface } from "./ObserverSurface"

vi.mock("../api/observer", () => ({
  nextObserverFrame: vi.fn().mockResolvedValue(null),
  openObserverSession: vi.fn().mockResolvedValue("observer-capability"),
  warmObserverAssets: vi.fn().mockResolvedValue(undefined),
}))

describe("ObserverSurface", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: true,
    })
  })

  it("allows insecure HTTP only for a private LAN IPv4 address", () => {
    expect(isObserverContextAllowed({ hostname: "192.168.31.224", protocol: "http:" }, false)).toBe(true)
    expect(isObserverContextAllowed({ hostname: "10.0.0.8", protocol: "http:" }, false)).toBe(true)
    expect(isObserverContextAllowed({ hostname: "172.16.0.8", protocol: "http:" }, false)).toBe(true)
    expect(isObserverContextAllowed({ hostname: "8.8.8.8", protocol: "http:" }, false)).toBe(false)
  })

  it("returns to idle immediately when observation ends", async () => {
    // Given: a supported local Observer that has started loading a room.
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
      configurable: true,
      value: () => ({}),
    })
    const user = userEvent.setup()
    renderLocalized(<ObserverProvider csrfToken="csrf" enabled><ObserverSurface bedCount={4} kind="room" roomId="local-nest" title="房间 3D 观察" /></ObserverProvider>)
    await user.click(screen.getByRole("button", { name: "进入 3D" }))
    expect(await screen.findByRole("button", { name: "结束观察" })).toBeInTheDocument()

    // When: the user ends the observation.
    await user.click(screen.getByRole("button", { name: "结束观察" }))

    // Then: the visible surface is idle without waiting for delayed engine release.
    expect(screen.getByRole("button", { name: "进入 3D" })).toBeInTheDocument()
    expect(screen.getByText("3D 将在首次打开时加载；聊天与管理不会因此等待。")).toBeInTheDocument()
  })

  it("resumes an already-ready engine without waiting for another ready event", async () => {
    // Given: an Observer engine that became ready and was then parked by the user.
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
      configurable: true,
      value: () => ({}),
    })
    const user = userEvent.setup()
    const { container } = renderLocalized(<ObserverProvider csrfToken="csrf" enabled><ObserverSurface bedCount={4} kind="room" roomId="local-nest" title="房间 3D 观察" /></ObserverProvider>)
    await user.click(screen.getByRole("button", { name: "进入 3D" }))
    const engine = container.querySelector<HTMLIFrameElement>("iframe[title='ElfieNest 3D Observer']")
    if (engine?.contentWindow === null || engine === null) throw new Error("observer iframe missing")
    window.dispatchEvent(new MessageEvent("message", { data: "elfienest:godot-web-ready", origin: window.location.origin, source: engine.contentWindow }))
    await act(async () => {})
    await user.click(screen.getByRole("button", { name: "结束观察" }))

    // When: observation resumes with the same engine.
    await user.click(screen.getByRole("button", { name: "进入 3D" }))

    // Then: the ready viewport returns without another loading handshake.
    expect(screen.queryByText("正在建立本地观察视角…")).toBeNull()
    expect(container.querySelectorAll("iframe[title='ElfieNest 3D Observer']")).toHaveLength(1)
  })

  it("can auto-start without rendering its own header controls inside a dialog", async () => {
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
      configurable: true,
      value: () => ({}),
    })

    renderLocalized(<ObserverProvider csrfToken="csrf" enabled><ObserverSurface autoStart bedCount={4} kind="room" roomId="local-nest" showHeader={false} title="房间 3D 观察" /></ObserverProvider>)

    expect(screen.getByRole("region", { name: "房间 3D 观察" })).toBeInTheDocument()
    expect(screen.queryByText("房间 3D 观察")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "进入 3D" })).not.toBeInTheDocument()
    expect(openObserverSession).toHaveBeenCalledWith({ kind: "room", room_id: "local-nest" }, "csrf")
  })

  it("explains unsupported HTTP instead of loading the Godot iframe", async () => {
    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: false,
    })
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
      configurable: true,
      value: () => ({}),
    })

    renderLocalized(<ObserverProvider csrfToken="csrf" enabled><ObserverSurface autoStart bedCount={4} kind="room" roomId="local-nest" showHeader={false} title="房间 3D 观察" /></ObserverProvider>)

    expect(await screen.findByText("手机浏览器需要安全连接才能打开 3D 房间观察。")).toBeInTheDocument()
    expect(screen.getByText(/10\.\*、172\.16\.\*–172\.31\.\*、192\.168\.\* 地址可以直接打开/)).toBeInTheDocument()
    expect(openObserverSession).not.toHaveBeenCalled()
  })

  it("renders the real fallback surface in English without Chinese copy", () => {
    renderLocalized(<ObserverSurface bedCount={4} kind="room" roomId="local-nest" title="3D room monitor" />, "en-US")

    expect(screen.getByText("3D monitoring is unavailable.")).toBeInTheDocument()
    expect(screen.getByText("Chat, profiles, and room management remain available.")).toBeInTheDocument()
    expect(screen.queryByText("当前无法运行 3D 观察。")).not.toBeInTheDocument()
  })
})

function renderLocalized(children: ReactNode, locale: SupportedLocale = "zh-CN") {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  return render(<I18nextProvider i18n={instance}>{children}</I18nextProvider>)
}
