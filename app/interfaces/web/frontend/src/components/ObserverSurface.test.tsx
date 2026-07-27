import { act, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { ObserverProvider } from "../stores/observer"
import { ObserverSurface } from "./ObserverSurface"

vi.mock("../api/observer", () => ({
  nextObserverFrame: vi.fn().mockResolvedValue(null),
  openObserverSession: vi.fn().mockResolvedValue("observer-capability"),
  warmObserverAssets: vi.fn().mockResolvedValue(undefined),
}))

describe("ObserverSurface", () => {
  it("returns to idle immediately when observation ends", async () => {
    // Given: a supported local Observer that has started loading a room.
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
      configurable: true,
      value: () => ({}),
    })
    const user = userEvent.setup()
    render(<ObserverProvider csrfToken="csrf" enabled><ObserverSurface kind="room" roomId="local-nest" title="房间 3D 观察" /></ObserverProvider>)
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
    const { container } = render(<ObserverProvider csrfToken="csrf" enabled><ObserverSurface kind="room" roomId="local-nest" title="房间 3D 观察" /></ObserverProvider>)
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
})
