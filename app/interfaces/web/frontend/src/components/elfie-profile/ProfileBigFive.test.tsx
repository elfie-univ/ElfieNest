import { act, render, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"

import { HAPPY_EXPERIENCE } from "./mock-data"
import { ProfileBigFive } from "./ProfileBigFive"
import type { ProfileChartRuntime } from "./ProfileChart"

createI18n()

function chartRuntime() {
  const chart = { dispose: vi.fn(), resize: vi.fn(), setOption: vi.fn() }
  return { chart, runtime: { init: vi.fn(() => chart) } satisfies ProfileChartRuntime }
}

describe("ProfileBigFive", () => {
  it("renders a public read-only radar with values and strongest descriptors", () => {
    const { container } = render(
      <ProfileBigFive
        elfieId={HAPPY_EXPERIENCE.publicProfile.elfieId}
        values={HAPPY_EXPERIENCE.publicProfile.bigFive}
      />,
    )

    const values = screen.getByRole("list", { name: "大五人格数值" })
    expect(within(values).getAllByRole("listitem")).toHaveLength(5)
    expect(values).toHaveTextContent("亲和70 分")
    expect(screen.getByRole("list", { name: "突出人格特征" })).toHaveTextContent("亲和")
    expect(container).not.toHaveTextContent("修改")
  })

  it("places the chart before descriptors for responsive DOM order", () => {
    const { container } = render(
      <ProfileBigFive
        elfieId={HAPPY_EXPERIENCE.publicProfile.elfieId}
        values={HAPPY_EXPERIENCE.publicProfile.bigFive}
      />,
    )
    const radar = container.querySelector(".profile-radar__chart")
    const descriptors = container.querySelector(".profile-radar__descriptors")

    if (radar === null || descriptors === null) throw new TypeError("Expected radar regions")
    expect(radar.compareDocumentPosition(descriptors) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it("re-resolves canvas colors when the document theme changes after render", async () => {
    const root = document.documentElement
    const disconnect = vi.spyOn(MutationObserver.prototype, "disconnect")
    const loaded = chartRuntime()
    const loadRuntime = () => Promise.resolve(loaded.runtime)
    root.dataset["theme"] = "test-initial"
    root.style.setProperty("--accent", "initial-accent")
    root.style.setProperty("--border", "initial-border")
    root.style.setProperty("--surface-raised", "initial-surface")
    root.style.setProperty("--text", "initial-text")
    root.style.setProperty("--text-muted", "initial-muted")

    const view = render(
      <ProfileBigFive
        elfieId={HAPPY_EXPERIENCE.publicProfile.elfieId}
        loadChartRuntime={loadRuntime}
        values={HAPPY_EXPERIENCE.publicProfile.bigFive}
      />,
    )
    await waitFor(() => expect(loaded.chart.setOption).toHaveBeenLastCalledWith(
      expect.objectContaining({ color: ["initial-accent"] }),
    ))

    act(() => {
      root.style.setProperty("--accent", "live-accent")
      root.style.setProperty("--border", "live-border")
      root.style.setProperty("--surface-raised", "live-surface")
      root.style.setProperty("--text", "live-text")
      root.style.setProperty("--text-muted", "live-muted")
      root.dataset["theme"] = "test-live"
    })

    await waitFor(() => expect(loaded.chart.setOption).toHaveBeenLastCalledWith(
      expect.objectContaining({
        color: ["live-accent"],
        textStyle: { color: "live-text" },
      }),
    ), { timeout: 3_000 })
    expect(loaded.chart.dispose).not.toHaveBeenCalled()
    view.unmount()
    expect(disconnect).toHaveBeenCalled()
    expect(loaded.chart.dispose).toHaveBeenCalledOnce()

    root.removeAttribute("data-theme")
    for (const property of ["--accent", "--border", "--surface-raised", "--text", "--text-muted"]) {
      root.style.removeProperty(property)
    }
    disconnect.mockRestore()
  })
})
