import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import type { ElfieProfile } from "../api/client"
import { ElfieProfilePanel } from "./ElfieProfilePanel"

const profile = {
  elfie_id: "elfie-happy",
  name: "Happy",
  species_id: "fox",
  gender: null,
  birth_date: null,
  summary: null,
  online_status: "unknown",
  portrait_url: "",
  appearance: {
    species_id: "fox",
    height_scale: 1.08,
    build_scale: 0.94,
    height_label: "tall",
    build_label: "slim",
    bone_scales: { HeadScale: 1.03 },
    material_parameters: { coat_palette: "silver" },
  },
  big_five: {},
  personality_tags: ["好奇探索", "extraversion", "openness"],
  nest: { room_name: "Local Nest", bed_name: "01号床", posture: "resting" },
  embodiment: { state: "at_nest" },
} satisfies ElfieProfile

describe("ElfieProfilePanel", () => {
  it("shows only user-meaningful scalar appearance fields", () => {
    // Given: a public profile containing user-facing labels and nested Runtime parameters.
    render(<ElfieProfilePanel profile={profile} />)

    // When: the appearance summary is rendered.
    const appearance = screen.getByText("身高：高挑 · 体型：轻盈")

    // Then: internal groups and object coercion never reach the product surface.
    expect(appearance).toBeInTheDocument()
    expect(screen.queryByText(/bone_scales|material_parameters|\[object Object\]/)).toBeNull()
  })

  it("translates internal profile enums into reader-facing identity copy", () => {
    render(<ElfieProfilePanel profile={profile} />)

    expect(screen.getByText("狐狸精灵 · 在精灵巢")).toBeInTheDocument()
    expect(screen.getByText("档案编号：HAPPY")).toBeInTheDocument()
    expect(screen.getByText("01号床 · 姿态 休息中")).toBeInTheDocument()
    expect(screen.getByText("好奇探索")).toBeInTheDocument()
    expect(screen.getAllByText("外向").length).toBeGreaterThan(0)
    expect(screen.getAllByText("开放").length).toBeGreaterThan(0)
    expect(screen.queryByText("fox · at_nest")).toBeNull()
    expect(screen.queryByText("elfie-happy")).toBeNull()
    expect(screen.queryByText("extraversion")).toBeNull()
    expect(screen.queryByText("openness")).toBeNull()
  })

  it("does not present camera controls without real observer handlers", () => {
    // Given: an Elfie profile with its Observer surface.
    render(<ElfieProfilePanel profile={profile} />)

    // When: the stage actions are inspected.
    const unsupportedActions = ["向左旋转", "向右旋转", "缩小", "放大", "回到房间", "查看精灵"]

    // Then: no unsupported control is exposed as an interactive button.
    for (const name of unsupportedActions) {
      expect(screen.queryByRole("button", { name })).toBeNull()
    }
  })
})
