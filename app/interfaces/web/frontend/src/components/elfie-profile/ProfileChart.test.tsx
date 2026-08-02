import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"

import { ProfileChart, type ProfileChartRuntime } from "./ProfileChart"

createI18n()

function runtime() {
  const chart = {
    dispose: vi.fn(),
    resize: vi.fn(),
    setOption: vi.fn(),
  }
  return { chart, runtime: { init: vi.fn(() => chart) } satisfies ProfileChartRuntime }
}

describe("ProfileChart", () => {
  it("shows a semantic summary while the lazy runtime loads", async () => {
    const pending = new Promise<ProfileChartRuntime>(() => undefined)
    render(
      <ProfileChart
        chartKey="12345678"
        label="大五人格雷达图"
        loadRuntime={() => pending}
        option={{}}
        summary={<p>开放 82 分</p>}
      />,
    )

    expect(screen.getByText("图表加载中…")).toBeInTheDocument()
    expect(screen.getByText("开放 82 分")).toBeInTheDocument()
    expect(screen.getByLabelText("大五人格雷达图")).toBeInTheDocument()
  })

  it("resizes and disposes exactly once on an Elfie key switch", async () => {
    let resizeCallback: () => void = () => undefined
    const disconnect = vi.fn()
    const observe = vi.fn()
    const OriginalResizeObserver = globalThis.ResizeObserver
    globalThis.ResizeObserver = class implements ResizeObserver {
      constructor(callback: ResizeObserverCallback) { resizeCallback = () => callback([], this) }
      disconnect = disconnect
      observe = observe
      unobserve(): void {}
    }
    const first = runtime()
    const second = runtime()
    const loadRuntime = vi.fn()
      .mockResolvedValueOnce(first.runtime)
      .mockResolvedValueOnce(second.runtime)

    const view = render(
      <ProfileChart chartKey="12345678" label="雷达" loadRuntime={loadRuntime} option={{ first: true }} summary="摘要" />,
    )
    await waitFor(() => expect(first.runtime.init).toHaveBeenCalledOnce())
    resizeCallback()
    expect(first.chart.resize).toHaveBeenCalledOnce()

    view.rerender(
      <ProfileChart chartKey="23456789" label="雷达" loadRuntime={loadRuntime} option={{ second: true }} summary="摘要" />,
    )
    await waitFor(() => expect(second.runtime.init).toHaveBeenCalledOnce())
    expect(first.chart.dispose).toHaveBeenCalledOnce()
    expect(disconnect).toHaveBeenCalledOnce()

    view.unmount()
    expect(second.chart.dispose).toHaveBeenCalledOnce()
    expect(disconnect).toHaveBeenCalledTimes(2)
    globalThis.ResizeObserver = OriginalResizeObserver
  })

  it("keeps the text alternative and reports a lazy-load failure", async () => {
    render(
      <ProfileChart
        chartKey="12345678"
        label="大五人格雷达图"
        loadRuntime={() => Promise.reject(new Error("blocked"))}
        option={{}}
        summary="亲和 91 分"
      />,
    )

    expect(await screen.findByRole("alert")).toHaveTextContent("图表暂时无法显示，请稍后重试。")
    expect(screen.getByText("亲和 91 分")).toBeInTheDocument()
  })
})
