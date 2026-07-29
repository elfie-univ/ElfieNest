import { act, renderHook } from "@testing-library/react"
import { useRef } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { PRODUCT_OBSERVER_URL, useObserverCameraBridge } from "./observer-camera-bridge"

function cameraCatalog(revision = 1) {
  return {
    channel: "elfienest.observer",
    version: 1,
    kind: "camera_catalog",
    revision,
    views: [
      { id: "overview", label: "总览" },
      { id: "dorm-01", label: "宿舍区" },
    ],
    active_id: "overview",
    presentation_paused: false,
  }
}

function appendProductEngine(): HTMLIFrameElement {
  const engine = document.createElement("iframe")
  engine.dataset["observerCameraTestEngine"] = "true"
  engine.src = PRODUCT_OBSERVER_URL
  document.body.appendChild(engine)
  if (engine.contentWindow === null) throw new Error("observer iframe missing")
  return engine
}

function dispatchCatalog(engine: HTMLIFrameElement, data: unknown, origin = window.location.origin): void {
  const source = engine.contentWindow
  if (source === null) throw new Error("observer iframe missing")
  window.dispatchEvent(new MessageEvent("message", { data, origin, source }))
}

function useBridgeHarness() {
  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  return { bridge: useObserverCameraBridge(iframeRef), iframeRef }
}

afterEach(() => {
  document.querySelectorAll("iframe[data-observer-camera-test-engine='true']").forEach((engine) => engine.remove())
})

describe("useObserverCameraBridge", () => {
  it("accepts a catalog only from its current same-origin iframe", () => {
    const { result } = renderHook(useBridgeHarness)
    const engine = appendProductEngine()
    const untrustedEngine = appendProductEngine()
    result.current.iframeRef.current = engine

    act(() => { dispatchCatalog(engine, JSON.stringify(cameraCatalog())) })

    expect(result.current.bridge.cameraCatalog).toMatchObject({ revision: 1, activeId: "overview" })
    act(() => { dispatchCatalog(engine, JSON.stringify(cameraCatalog(2)), "https://untrusted.example") })
    act(() => { dispatchCatalog(untrustedEngine, JSON.stringify(cameraCatalog(2))) })
    act(() => { dispatchCatalog(engine, JSON.stringify({ ...cameraCatalog(2), camera_position: { x: 1, y: 2, z: 3 } })) })

    expect(result.current.bridge.cameraCatalog).toMatchObject({ revision: 1, activeId: "overview" })
  })

  it("ignores a catalog when the current same-origin iframe leaves the product observer URL", () => {
    const { result } = renderHook(useBridgeHarness)
    const engine = appendProductEngine()
    result.current.iframeRef.current = engine
    act(() => { dispatchCatalog(engine, JSON.stringify(cameraCatalog())) })
    engine.src = "/runtime/godot/elfienest.html?observer=diagnostic"

    act(() => { dispatchCatalog(engine, JSON.stringify(cameraCatalog(2))) })

    expect(result.current.bridge.cameraCatalog).toMatchObject({ revision: 1, activeId: "overview" })
  })

  it("sends only exact high-level commands for known camera views", () => {
    const { result } = renderHook(useBridgeHarness)
    const engine = appendProductEngine()
    const target = engine.contentWindow
    if (target === null) throw new Error("observer iframe missing")
    result.current.iframeRef.current = engine
    act(() => { dispatchCatalog(engine, JSON.stringify(cameraCatalog())) })
    const postMessage = vi.spyOn(target, "postMessage")

    act(() => {
      result.current.bridge.overview()
      result.current.bridge.select("dorm-01")
      result.current.bridge.reset()
      result.current.bridge.setLocalPresentationPaused(true)
      result.current.bridge.select("unknown-view")
    })

    expect(postMessage).toHaveBeenNthCalledWith(1, {
      channel: "elfienest.observer",
      version: 1,
      kind: "camera_command",
      action: "overview",
    }, window.location.origin)
    expect(postMessage).toHaveBeenNthCalledWith(2, {
      channel: "elfienest.observer",
      version: 1,
      kind: "camera_command",
      action: "select",
      view_id: "dorm-01",
    }, window.location.origin)
    expect(postMessage).toHaveBeenNthCalledWith(3, {
      channel: "elfienest.observer",
      version: 1,
      kind: "camera_command",
      action: "reset",
    }, window.location.origin)
    expect(postMessage).toHaveBeenNthCalledWith(4, {
      channel: "elfienest.observer",
      version: 1,
      kind: "camera_command",
      action: "set_local_presentation_paused",
      paused: true,
    }, window.location.origin)
    expect(postMessage).toHaveBeenCalledTimes(4)
  })

  it("keeps the mounted iframe and catalog intact when local pause is requested", () => {
    const { result } = renderHook(useBridgeHarness)
    const engine = appendProductEngine()
    const target = engine.contentWindow
    if (target === null) throw new Error("observer iframe missing")
    result.current.iframeRef.current = engine
    act(() => { dispatchCatalog(engine, JSON.stringify(cameraCatalog())) })
    const catalogBeforePause = result.current.bridge.cameraCatalog
    const postMessage = vi.spyOn(target, "postMessage")

    act(() => { result.current.bridge.setLocalPresentationPaused(true) })

    expect(engine.isConnected).toBe(true)
    expect(engine.parentElement).toBe(document.body)
    expect(result.current.bridge.cameraCatalog).toBe(catalogBeforePause)
    expect(postMessage).toHaveBeenCalledTimes(1)
  })

  it("does not post after the iframe changes away from the product observer URL", () => {
    const { result } = renderHook(useBridgeHarness)
    const engine = appendProductEngine()
    const target = engine.contentWindow
    if (target === null) throw new Error("observer iframe missing")
    result.current.iframeRef.current = engine
    const postMessage = vi.spyOn(target, "postMessage")
    engine.src = "https://untrusted.example/observer.html"

    act(() => { result.current.bridge.overview() })

    expect(postMessage).not.toHaveBeenCalled()
  })

  it("freezes local camera commands while the engine catalog reports presentation paused", () => {
    const { result } = renderHook(useBridgeHarness)
    const engine = appendProductEngine()
    const target = engine.contentWindow
    if (target === null) throw new Error("observer iframe missing")
    result.current.iframeRef.current = engine
    act(() => { dispatchCatalog(engine, JSON.stringify({ ...cameraCatalog(), presentation_paused: true })) })
    const postMessage = vi.spyOn(target, "postMessage")

    act(() => {
      result.current.bridge.reset()
      result.current.bridge.overview()
      result.current.bridge.select("dorm-01")
      result.current.bridge.setLocalPresentationPaused(false)
    })

    expect(postMessage).toHaveBeenCalledOnce()
    expect(postMessage).toHaveBeenCalledWith({
      channel: "elfienest.observer",
      version: 1,
      kind: "camera_command",
      action: "set_local_presentation_paused",
      paused: false,
    }, window.location.origin)
  })
})
