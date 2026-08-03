import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { createI18n } from "../../i18n/config"

import { HAPPY_EXPERIENCE } from "./mock-data"
import { ProfileImportantExperiences } from "./ProfileImportantExperiences"
import type { ImportantExperiences } from "./model"

createI18n()

describe("ProfileImportantExperiences", () => {
  it("shows lifetime events newest first with one visible marker per event", () => {
    render(<ProfileImportantExperiences experiences={HAPPY_EXPERIENCE.privateCognition.importantExperiences} status="ready" />)

    const timeline = screen.getByRole("list", { name: "重要经历时间线" })
    const items = timeline.querySelectorAll(".profile-private-experiences__item")

    expect(items).toHaveLength(2)
    expect(timeline.querySelectorAll(".profile-private-experiences__marker")).toHaveLength(2)
    expect(items[0]?.querySelector("time")).toHaveAttribute("datetime", "2026-07-04")
    expect(items[1]?.querySelector("time")).toHaveAttribute("datetime", "2026-06-30")
  })

  it("caps visible lifetime events at ten", () => {
    const experiences: ImportantExperiences = {
      entries: Array.from({ length: 11 }, (_, index) => ({
        id: `event:${index}`,
        occurredAt: `2026-07-${String(index + 1).padStart(2, "0")}`,
        title: `事件 ${index}`,
        changed: "发生了重要变化。",
        importance: 1,
        people: [],
      })),
    }

    render(<ProfileImportantExperiences experiences={experiences} status="ready" />)

    expect(screen.getByRole("list", { name: "重要经历时间线" }).querySelectorAll(".profile-private-experiences__item")).toHaveLength(10)
  })
})
