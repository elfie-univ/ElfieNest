import { render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import * as client from "../api/client"
import { AdoptionPanel } from "../components/AdoptionPanel"
import { LoginPage } from "./LoginPage"
import { SetupPage } from "./SetupPage"

describe("auth and adoption field rows", () => {
  it("renders login fields as horizontal field rows with unique labels", () => {
    render(<LoginPage />)

    expect(screen.getAllByLabelText("账号").some((node) => node.tagName === "INPUT")).toBe(true)
    expect(screen.getAllByLabelText("密码").some((node) => node.tagName === "INPUT")).toBe(true)
  })

  it("keeps setup true fields as rows while the fallback confirmation remains checkbox copy", () => {
    render(<SetupPage />)

    expect(screen.getByLabelText("管理员账号")).toBeInTheDocument()
    expect(screen.getByLabelText("密码")).toBeInTheDocument()
  })

  it("renders adoption inputs and selects as true field rows", async () => {
    vi.spyOn(client, "adoptionInfo").mockResolvedValue({
      builds: ["轻盈"],
      heights: ["小型"],
      personality_styles: ["温和"],
      quota: { can_adopt: true, max: 2, remaining: 1, used: 1 },
      species_ids: ["cat"],
    })

    render(<AdoptionPanel csrfToken="csrf" onAdopted={async () => undefined} />)

    for (const label of ["精灵名字", "物种", "人格风格", "身高", "体型"]) {
      const field = await screen.findByRole("group", { name: label })
      expect(within(field).getByLabelText(label)).toBeInTheDocument()
    }
  })
})
