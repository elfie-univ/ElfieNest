import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { act, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"

import { HAPPY_EXPERIENCE } from "../../test/fixtures/elfie-profile"
import { ProfileBigFive } from "./ProfileBigFive"
import type { ProfileChartRuntime } from "./ProfileChart"

createI18n()

const profileStyles = readFileSync(resolve(import.meta.dirname, "../../shared/chat-profile.css"), "utf8")

function chartRuntime() {
  const chart = { dispose: vi.fn(), resize: vi.fn(), setOption: vi.fn() }
  return { chart, runtime: { init: vi.fn(() => chart) } satisfies ProfileChartRuntime }
}

describe("ProfileBigFive", () => {
  it("keeps the inner-portrait label subordinate and shows only the key traits", () => {
    const { container } = render(
      <ProfileBigFive
        elfieId={HAPPY_EXPERIENCE.publicProfile.elfieId}
        values={HAPPY_EXPERIENCE.publicProfile.bigFive}
      />,
    )

    expect(screen.getByText("大五人格", { selector: ".profile-dossier__section-name" })).toBeInTheDocument()
    expect(screen.queryByRole("heading", { name: "大五人格" })).not.toBeInTheDocument()
    expect(screen.getByText("内在画像", { selector: "span" })).toBeInTheDocument()
    expect(screen.getByRole("list", { name: "大五人格数值" })).toHaveClass("profile-radar__values--accessible")
    expect(screen.queryByText("亲和70 分")).not.toBeInTheDocument()
    expect(screen.getByRole("list", { name: "突出人格特征" })).toHaveTextContent("亲和")
    expect(screen.getByRole("list", { name: "突出人格特征" })).not.toHaveTextContent("重视合作和温柔回应")
    expect(container.querySelector(".profile-radar")).toHaveClass("profile-radar--compact")
    expect(container.querySelector(".profile-radar__content")).toBeInTheDocument()
    expect(container.querySelectorAll(".profile-radar__descriptor")).toHaveLength(3)
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

  it("keeps the radar chart at a stable size instead of letting the side list squeeze it", () => {
    const compactCanvasRule = [...profileStyles.matchAll(
      /\.profile-radar--compact \.profile-chart__canvas\s*\{[^}]+\}/g,
    )].map(([rule]) => rule).find((rule) => rule.includes("height: 360px")) ?? ""

    expect(compactCanvasRule).toContain("width: 360px")
    expect(compactCanvasRule).toContain("height: 360px")
    expect(compactCanvasRule).toContain("aspect-ratio: 1")
    expect(compactCanvasRule).not.toContain("clamp")
  })

  it("keeps descriptor cards secondary and stacks them without shrinking the radar", () => {
    const compactContentRule = profileStyles.match(
      /\.profile-radar--compact \.profile-radar__content\s*\{[^}]+\}/,
    )?.[0] ?? ""
    const descriptorRule = profileStyles.match(
      /\.profile-radar--compact \.profile-radar__descriptors\s*\{[^}]+\}/,
    )?.[0] ?? ""

    expect(compactContentRule).toContain("360px minmax(0, 320px)")
    expect(compactContentRule).toContain("gap: 16px")
    expect(descriptorRule).toContain("width: min(100%, 320px)")
    expect(descriptorRule).toContain("max-width: 100%")
    expect(profileStyles).toMatch(
      /\.profile-radar--compact \.profile-radar__descriptors ul,\s*\.profile-radar--compact \.profile-radar__descriptors li \{ width: 100%; \}/,
    )
    expect(profileStyles).toContain("background: color-mix(in srgb, var(--accent-soft) 72%, var(--surface-raised));")
    expect(profileStyles).toMatch(
      /@container \(max-width: 720px\)[\s\S]*\.profile-radar--compact \.profile-radar__content\s*\{[^}]*grid-template-columns: minmax\(0, 1fr\)/,
    )
    expect(profileStyles).toMatch(
      /@container \(max-width: 720px\)[\s\S]*\.profile-radar--compact \.profile-radar__descriptors\s*\{[^}]*width: 100%[^}]*max-width: none/,
    )
  })

  it("lays the three mobile descriptor cards out as equal columns", () => {
    const finalMobileRules = profileStyles.slice(profileStyles.indexOf("@media (max-width: 760px)"))
    const descriptorListRule = finalMobileRules.match(
      /\.profile-radar--compact \.profile-radar__descriptors ul\s*\{[^}]+\}/,
    )?.[0] ?? ""

    expect(descriptorListRule).toContain("grid-template-columns: repeat(3, minmax(0, 1fr));")
  })

  it("fills the available width when descriptors move below the chart", () => {
    const stackedContainerBlock = profileStyles.match(
      /@container \(max-width: 720px\) \{[\s\S]*?^\}/m,
    )?.[0] ?? ""

    expect(stackedContainerBlock).toContain("width: 100%;")
    expect(stackedContainerBlock).toContain("max-width: none;")
    expect(stackedContainerBlock).toContain("grid-template-columns: repeat(3, minmax(0, 1fr));")
    expect(stackedContainerBlock).toContain(".profile-radar--compact .profile-radar__descriptors li { width: 100%; min-width: 0; }")
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
