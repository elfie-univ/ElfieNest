import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { nextObserverFrame, openObserverSession } from "../api/observer"
import { ObserverProvider, useOptionalObserver } from "./observer"

vi.mock("../api/observer", () => ({
  nextObserverFrame: vi.fn().mockResolvedValue(null),
  openObserverSession: vi.fn().mockResolvedValue("observer-capability"),
  warmObserverAssets: vi.fn().mockResolvedValue(undefined),
}))

function CameraResetProbe() {
  const observer = useOptionalObserver()
  if (observer === null) throw new Error("ObserverProvider is required")
  return <>
    <button onClick={() => { void observer.openRoom("local-nest", { channel: "elfienest.observer", version: 1, kind: "world_config", nest_id: "local-nest", bed_count: 4 }) }} type="button">打开房间</button>
    <p>{observer.status}</p>
    <p data-testid="camera-catalog">{observer.cameraCatalog?.revision ?? "none"}</p>
  </>
}

function dispatchCatalog(engine: HTMLIFrameElement): void {
  const source = engine.contentWindow
  if (source === null) throw new Error("observer iframe missing")
  window.dispatchEvent(new MessageEvent("message", {
    data: JSON.stringify({
      channel: "elfienest.observer",
      version: 1,
      kind: "camera_catalog",
      revision: 1,
      views: [{ id: "overview", label: "总览" }],
      active_id: "overview",
      presentation_paused: false,
    }),
    origin: window.location.origin,
    source,
  }))
}

afterEach(() => {
  vi.useRealTimers()
  vi.mocked(nextObserverFrame).mockReset().mockResolvedValue(null)
  vi.mocked(openObserverSession).mockReset().mockResolvedValue("observer-capability")
})

describe("ObserverProvider camera catalog reset", () => {
  it("clears the catalog when the observer engine is reset after its readiness deadline", async () => {
    vi.useFakeTimers()
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { configurable: true, value: () => ({}) })
    const { container } = render(<ObserverProvider csrfToken="csrf" enabled><CameraResetProbe /></ObserverProvider>)

    fireEvent.click(screen.getByRole("button", { name: "打开房间" }))
    await act(async () => {})
    const engine = container.querySelector<HTMLIFrameElement>("iframe[title='ElfieNest 3D Observer']")
    if (engine?.contentWindow === null || engine === null) throw new Error("observer iframe missing")
    act(() => { dispatchCatalog(engine) })
    expect(screen.getByTestId("camera-catalog")).toHaveTextContent("1")

    await act(async () => { vi.advanceTimersByTime(20 * 1000) })

    expect(screen.getByText("fallback")).toBeInTheDocument()
    expect(container.querySelector("iframe[title='ElfieNest 3D Observer']")).toBeNull()
    expect(screen.getByTestId("camera-catalog")).toHaveTextContent("none")
  })
})
