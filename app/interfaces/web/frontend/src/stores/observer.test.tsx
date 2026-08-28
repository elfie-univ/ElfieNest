import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { closeObserverSession, nextObserverFrame, openObserverSession, type ObserverFrame } from "../api/observer"
import { ApiError } from "../api/http"
import { ObserverProvider, useOptionalObserver } from "./observer"

vi.mock("../api/observer", () => ({
  closeObserverSession: vi.fn().mockResolvedValue(undefined),
  nextObserverFrame: vi.fn().mockResolvedValue(null),
  openObserverSession: vi.fn().mockResolvedValue({ capability: "observer-capability", idleTimeoutSeconds: 120 }),
  warmObserverAssets: vi.fn().mockResolvedValue(undefined),
}))

function TestObserver() {
  const observer = useRequiredObserver()
  return <>
    <button onClick={() => { void observer.openRoom("local-nest", { channel: "elfienest.observer", version: 1, kind: "world_config", nest_id: "local-nest", bed_count: 4 }) }} type="button">打开房间</button>
    <button onClick={() => { void observer.openElfie("fox-1") }} type="button">打开精灵</button>
    <button onClick={observer.detach} type="button">离开 3D</button>
    <p>{observer.status}</p>
  </>
}

function useRequiredObserver() {
  const observer = useOptionalObserver()
  if (observer === null) throw new Error("ObserverProvider is required")
  return observer
}

afterEach(() => {
  vi.useRealTimers()
  vi.mocked(openObserverSession).mockReset().mockResolvedValue({ capability: "observer-capability", idleTimeoutSeconds: 120 })
  vi.mocked(closeObserverSession).mockReset().mockResolvedValue(undefined)
  vi.mocked(nextObserverFrame).mockReset().mockResolvedValue(null)
})

beforeEach(() => {
  Object.defineProperty(window, "isSecureContext", {
    configurable: true,
    value: true,
  })
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: "visible",
  })
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
    const postMessage = vi.spyOn(engine.contentWindow, "postMessage")
    window.dispatchEvent(new MessageEvent("message", {
      data: "elfienest:godot-web-ready",
      origin: window.location.origin,
      source: engine.contentWindow,
    }))
    await act(async () => {})

    expect(screen.getByText("ready")).toBeInTheDocument()
    expect(postMessage).toHaveBeenCalledWith({
      channel: "elfienest.observer",
      version: 1,
      kind: "world_config",
      nest_id: "local-nest",
      bed_count: 4,
    }, window.location.origin)
  })

  it("replays the latest semantic snapshot when the engine becomes ready", async () => {
    const snapshot = {
      protocol: 3,
      kind: "snapshot",
      generation: 1,
      sequence: 1,
      scope: { kind: "room", room_id: "local-nest" },
      entities: {
        "fox-1": {
          room_id: "local-nest",
          zone_id: "dorm",
          posture: "resting",
          active: true,
          active_command_id: null,
          species_id: "fox",
          appearance: {},
          home_anchor_id: "dorm-01/bed-01",
          mock_motion: null,
        },
      },
      entity_revisions: { "fox-1": 1 },
    } satisfies ObserverFrame
    let resolveFrame: ((frame: ObserverFrame) => void) | undefined
    vi.mocked(nextObserverFrame).mockImplementationOnce(() => new Promise((resolve) => {
      resolveFrame = resolve
    }))
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { configurable: true, value: () => ({}) })
    const { container } = render(<ObserverProvider csrfToken="csrf" enabled><TestObserver /></ObserverProvider>)

    fireEvent.click(screen.getByRole("button", { name: "打开房间" }))
    await act(async () => {})
    const engine = container.querySelector<HTMLIFrameElement>("iframe[title='ElfieNest 3D Observer']")
    if (engine?.contentWindow === null || engine === null || resolveFrame === undefined) throw new Error("observer iframe missing")
    const postMessage = vi.spyOn(engine.contentWindow, "postMessage")

    resolveFrame(snapshot)
    await act(async () => {})
    expect(postMessage.mock.calls.filter(([value]) => (
      typeof value === "object" && value !== null && Reflect.get(value, "kind") === "semantic_snapshot"
    ))).toHaveLength(1)

    window.dispatchEvent(new MessageEvent("message", {
      data: "elfienest:godot-web-ready",
      origin: window.location.origin,
      source: engine.contentWindow,
    }))
    await act(async () => {})

    expect(postMessage).toHaveBeenCalledWith(expect.objectContaining({
      kind: "semantic_snapshot",
      entities: expect.objectContaining({ "fox-1": expect.any(Object) }),
    }), window.location.origin)
    expect(postMessage.mock.calls.filter(([value]) => (
      typeof value === "object" && value !== null && Reflect.get(value, "kind") === "semantic_snapshot"
    ))).toHaveLength(2)
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

  it("stops polling immediately and releases the renderer after one warm minute", async () => {
    vi.useFakeTimers()
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { configurable: true, value: () => ({}) })
    const { container } = render(<ObserverProvider csrfToken="csrf" enabled><TestObserver /></ObserverProvider>)

    fireEvent.click(screen.getByRole("button", { name: "打开房间" }))
    await act(async () => {})
    const engine = container.querySelector<HTMLIFrameElement>("iframe[title='ElfieNest 3D Observer']")
    if (engine?.contentWindow === null || engine === null) throw new Error("observer iframe missing")
    window.dispatchEvent(new MessageEvent("message", {
      data: "elfienest:godot-web-ready",
      origin: window.location.origin,
      source: engine.contentWindow,
    }))
    await act(async () => {})
    expect(container.querySelectorAll("iframe[title='ElfieNest 3D Observer']")).toHaveLength(1)

    const pollCount = vi.mocked(nextObserverFrame).mock.calls.length
    const closeCount = vi.mocked(closeObserverSession).mock.calls.length
    fireEvent.click(screen.getByRole("button", { name: "离开 3D" }))
    await act(async () => { vi.advanceTimersByTime(59 * 1000) })
    expect(container.querySelector("iframe[title='ElfieNest 3D Observer']")).not.toBeNull()
    expect(nextObserverFrame).toHaveBeenCalledTimes(pollCount)
    await act(async () => { vi.advanceTimersByTime(1000) })
    expect(container.querySelector("iframe[title='ElfieNest 3D Observer']")).toBeNull()
    expect(closeObserverSession).toHaveBeenCalledTimes(closeCount)
  })

  it("pauses in a hidden tab and reuses the same session after a quick return", async () => {
    vi.useFakeTimers()
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { configurable: true, value: () => ({}) })
    const { container } = render(<ObserverProvider csrfToken="csrf" enabled><TestObserver /></ObserverProvider>)

    fireEvent.click(screen.getByRole("button", { name: "打开房间" }))
    await act(async () => {})
    const engine = container.querySelector<HTMLIFrameElement>("iframe[title='ElfieNest 3D Observer']")
    if (engine?.contentWindow === null || engine === null) throw new Error("observer iframe missing")
    window.dispatchEvent(new MessageEvent("message", {
      data: "elfienest:godot-web-ready",
      origin: window.location.origin,
      source: engine.contentWindow,
    }))
    await act(async () => {})
    const pollCount = vi.mocked(nextObserverFrame).mock.calls.length
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" })
    document.dispatchEvent(new Event("visibilitychange"))
    await act(async () => { vi.advanceTimersByTime(30 * 1000) })

    expect(nextObserverFrame).toHaveBeenCalledTimes(pollCount)
    expect(container.querySelector("iframe[title='ElfieNest 3D Observer']")).toBe(engine)

    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" })
    document.dispatchEvent(new Event("visibilitychange"))
    await act(async () => {})

    expect(openObserverSession).toHaveBeenCalledTimes(1)
    expect(nextObserverFrame).toHaveBeenCalledTimes(pollCount + 1)
    expect(container.querySelector("iframe[title='ElfieNest 3D Observer']")).toBe(engine)
  })

  it("reopens an expired observer lease without destroying the renderer", async () => {
    vi.mocked(nextObserverFrame)
      .mockRejectedValueOnce(new ApiError(410, "expired", [], "observer_session_expired"))
      .mockResolvedValueOnce(null)
    vi.mocked(openObserverSession)
      .mockResolvedValueOnce({ capability: "expired-capability", idleTimeoutSeconds: 120 })
      .mockResolvedValueOnce({ capability: "renewed-capability", idleTimeoutSeconds: 120 })
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { configurable: true, value: () => ({}) })
    const { container } = render(<ObserverProvider csrfToken="csrf" enabled><TestObserver /></ObserverProvider>)

    fireEvent.click(screen.getByRole("button", { name: "打开房间" }))
    await act(async () => {})

    expect(openObserverSession).toHaveBeenCalledTimes(2)
    expect(nextObserverFrame).toHaveBeenNthCalledWith(
      2,
      "renewed-capability",
      null,
      expect.any(AbortSignal),
    )
    expect(container.querySelectorAll("iframe[title='ElfieNest 3D Observer']")).toHaveLength(1)
  })

  it("keeps the renderer and retries a transient frame failure", async () => {
    vi.useFakeTimers()
    vi.mocked(nextObserverFrame)
      .mockRejectedValueOnce(new Error("temporary network failure"))
      .mockResolvedValueOnce(null)
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { configurable: true, value: () => ({}) })
    const { container } = render(<ObserverProvider csrfToken="csrf" enabled><TestObserver /></ObserverProvider>)

    fireEvent.click(screen.getByRole("button", { name: "打开房间" }))
    await act(async () => {})
    const engine = container.querySelector("iframe[title='ElfieNest 3D Observer']")
    await act(async () => { vi.advanceTimersByTime(1000) })

    expect(nextObserverFrame).toHaveBeenCalledTimes(2)
    expect(openObserverSession).toHaveBeenCalledTimes(1)
    expect(container.querySelector("iframe[title='ElfieNest 3D Observer']")).toBe(engine)
  })

  it("best-effort closes the session when the page is really unloaded", async () => {
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { configurable: true, value: () => ({}) })
    render(<ObserverProvider csrfToken="csrf" enabled><TestObserver /></ObserverProvider>)
    fireEvent.click(screen.getByRole("button", { name: "打开房间" }))
    await act(async () => {})
    const event = new Event("pagehide")
    Object.defineProperty(event, "persisted", { value: false })

    window.dispatchEvent(event)
    await act(async () => {})

    expect(closeObserverSession).toHaveBeenCalledWith(
      "observer-capability",
      "csrf",
      true,
    )
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
    expect(openObserverSession).toHaveBeenCalledTimes(1)
  })

  it("recreates the same room observer after a capability handshake failure", async () => {
    vi.mocked(openObserverSession)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({ capability: "retry-capability", idleTimeoutSeconds: 120 })
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
          species_id: null,
          appearance: {},
          home_anchor_id: null,
          mock_motion: null,
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
      const observer = useRequiredObserver()
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
