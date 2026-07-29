import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { nextObserverFrame, openObserverSession, type ObserverFrame } from "../api/observer"
import { ObserverProvider, useObserver } from "./observer"

vi.mock("../api/observer", () => ({
  nextObserverFrame: vi.fn().mockResolvedValue(null),
  openObserverSession: vi.fn().mockResolvedValue("observer-capability"),
  updateObserverInterest: vi.fn().mockResolvedValue(undefined),
  warmObserverAssets: vi.fn().mockResolvedValue(undefined),
}))

function TestObserver() {
  const observer = useObserver()
  return <>
    <button onClick={() => { void observer.openRoom("local-nest") }} type="button">打开房间</button>
    <button onClick={() => { void observer.openElfie("fox-1") }} type="button">打开精灵</button>
    <button onClick={observer.detach} type="button">离开 3D</button>
    <p>{observer.status}</p>
  </>
}

afterEach(() => {
  vi.useRealTimers()
  vi.mocked(openObserverSession).mockReset().mockResolvedValue("observer-capability")
  vi.mocked(nextObserverFrame).mockReset().mockResolvedValue(null)
})

describe("ObserverProvider", () => {
  it("accepts only the same-origin ready message from its observer iframe", async () => {
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { configurable: true, value: () => ({}) })
    const { container } = render(<ObserverProvider csrfToken="csrf" enabled><TestObserver /></ObserverProvider>)

    fireEvent.click(screen.getByRole("button", { name: "打开房间" }))
    await act(async () => {})
    const engine = container.querySelector<HTMLIFrameElement>("iframe[title='ElfieNest 3D Observer']")
    if (engine?.contentWindow === null || engine === null) throw new Error("observer iframe missing")
    expect(Reflect.get(engine, "allow")).toBeUndefined()
    window.dispatchEvent(new MessageEvent("message", {
      data: "elfienest:godot-web-ready",
      origin: window.location.origin,
      source: engine.contentWindow,
    }))
    await act(async () => {})

    expect(screen.getByText("ready")).toBeInTheDocument()
  })

  it("marks the observer ready when the same-origin Godot export reaches canvas without a ready message", async () => {
    vi.useFakeTimers()
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { configurable: true, value: () => ({}) })
    const { container } = render(<ObserverProvider csrfToken="csrf" enabled><TestObserver /></ObserverProvider>)

    fireEvent.click(screen.getByRole("button", { name: "打开房间" }))
    await act(async () => {})
    const engine = container.querySelector<HTMLIFrameElement>("iframe[title='ElfieNest 3D Observer']")
    if (engine?.contentDocument === null || engine === null) throw new Error("observer iframe missing")
    expect(engine.getAttribute("src")).toBe("/runtime/godot/elfienest.html?observer=product")
    expect(screen.getByText("loading")).toBeInTheDocument()

    engine.contentDocument.open()
    engine.contentDocument.write("<!doctype html><html><body><canvas id=\"canvas\"></canvas></body></html>")
    engine.contentDocument.close()
    await act(async () => { vi.advanceTimersByTime(250) })

    expect(screen.getByText("ready")).toBeInTheDocument()
  })

  it("reuses one observer engine across room and Elfie scopes, then releases it after five idle minutes", async () => {
    vi.useFakeTimers()
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { configurable: true, value: () => ({}) })
    const { container } = render(<ObserverProvider csrfToken="csrf" enabled><TestObserver /></ObserverProvider>)

    fireEvent.click(screen.getByRole("button", { name: "打开房间" }))
    await act(async () => {})
    expect(container.querySelectorAll("iframe[title='ElfieNest 3D Observer']")).toHaveLength(1)

    fireEvent.click(screen.getByRole("button", { name: "打开精灵" }))
    await act(async () => {})
    expect(container.querySelectorAll("iframe[title='ElfieNest 3D Observer']")).toHaveLength(1)

    fireEvent.click(screen.getByRole("button", { name: "离开 3D" }))
    await act(async () => { vi.advanceTimersByTime(5 * 60 * 1000) })
    expect(container.querySelector("iframe[title='ElfieNest 3D Observer']")).toBeNull()
  })

  it("recreates the same room observer after its readiness deadline expires", async () => {
    vi.useFakeTimers()
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { configurable: true, value: () => ({}) })
    const { container } = render(<ObserverProvider csrfToken="csrf" enabled><TestObserver /></ObserverProvider>)

    fireEvent.click(screen.getByRole("button", { name: "打开房间" }))
    await act(async () => {})
    const firstEngine = container.querySelector<HTMLIFrameElement>("iframe[title='ElfieNest 3D Observer']")
    if (firstEngine?.contentWindow === null || firstEngine === null) throw new Error("first observer iframe missing")
    await act(async () => { vi.advanceTimersByTime(20 * 1000) })
    expect(screen.getByText("fallback")).toBeInTheDocument()
    expect(container.querySelector("iframe[title='ElfieNest 3D Observer']")).toBeNull()
    window.dispatchEvent(new MessageEvent("message", {
      data: "elfienest:godot-web-ready",
      origin: window.location.origin,
      source: firstEngine.contentWindow,
    }))
    await act(async () => {})
    expect(screen.getByText("fallback")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "打开房间" }))
    await act(async () => {})
    const secondEngine = container.querySelector<HTMLIFrameElement>("iframe[title='ElfieNest 3D Observer']")
    if (secondEngine?.contentWindow === null || secondEngine === null) throw new Error("second observer iframe missing")
    expect(secondEngine).not.toBe(firstEngine)
    window.dispatchEvent(new MessageEvent("message", {
      data: "elfienest:godot-web-ready",
      origin: window.location.origin,
      source: firstEngine.contentWindow,
    }))
    await act(async () => {})
    expect(screen.getByText("loading")).toBeInTheDocument()
    expect(openObserverSession).toHaveBeenCalledTimes(2)
  })

  it("recreates the same room observer after a capability handshake failure", async () => {
    vi.mocked(openObserverSession)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce("retry-capability")
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { configurable: true, value: () => ({}) })
    const { container } = render(<ObserverProvider csrfToken="csrf" enabled><TestObserver /></ObserverProvider>)

    fireEvent.click(screen.getByRole("button", { name: "打开房间" }))
    await act(async () => {})
    const failedEngine = container.querySelector("iframe[title='ElfieNest 3D Observer']")
    expect(screen.getByText("fallback")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "打开房间" }))
    await act(async () => {})
    expect(container.querySelector("iframe[title='ElfieNest 3D Observer']")).not.toBe(failedEngine)
    expect(openObserverSession).toHaveBeenCalledTimes(2)
  })

  it("applies nullable semantic fields as clears after the backend restores them", async () => {
    vi.useFakeTimers()
    const snapshot = {
      protocol: 3,
      kind: "snapshot",
      generation: 1,
      sequence: 1,
      scope: { kind: "elfie", elfie_id: "fox-1" },
      entities: {
        "fox-1": {
          room_id: "local-nest",
          zone_id: "dorm",
          posture: "resting",
          active: true,
          active_command_id: "rest-1",
        },
      },
      entity_revisions: { "fox-1": 1 },
    } satisfies ObserverFrame
    const cleared = {
      protocol: 3,
      kind: "delta",
      generation: 1,
      sequence: 2,
      scope: { kind: "elfie", elfie_id: "fox-1" },
      entity_id: "fox-1",
      entity_revision: 2,
      patch: { zone_id: null, active_command_id: null },
    } satisfies ObserverFrame
    vi.mocked(nextObserverFrame).mockResolvedValueOnce(snapshot).mockResolvedValueOnce(cleared)
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { configurable: true, value: () => ({}) })

    function SemanticProbe() {
      const observer = useObserver()
      const entity = observer.entities["fox-1"]
      return <><button onClick={() => { void observer.openElfie("fox-1") }} type="button">观察 Fox</button><p>{entity?.zone_id ?? "无区域"}|{entity?.active_command_id ?? "无命令"}</p></>
    }

    render(<ObserverProvider csrfToken="csrf" enabled><SemanticProbe /></ObserverProvider>)
    fireEvent.click(screen.getByRole("button", { name: "观察 Fox" }))
    await act(async () => {})
    expect(screen.getByText("dorm|rest-1")).toBeInTheDocument()
    await act(async () => { vi.advanceTimersByTime(1000) })
    expect(screen.getByText("无区域|无命令")).toBeInTheDocument()
  })
})
