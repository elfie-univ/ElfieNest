import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { FoodRoleTable } from "./FoodRoleTable"

describe("Owner food roles", () => {
  it("renders the five contract roles without model tuning fields", () => {
    const html = renderToStaticMarkup(createElement(FoodRoleTable, {
      food: {
        key: "food_common",
        display_name: "常用粮",
        system_role: "common",
        enabled: true,
        archived: false,
        roles: {
          primary: { model: "openai_api_0001/gpt" },
          reasoning: null,
          vision: null,
          tool: null,
          fallback: [],
        },
        health: "healthy",
        locality: "remote",
        latest_evidence_at: "2026-07-30T00:00:00+00:00",
      },
    }))
    for (const role of ["Primary", "Reasoning", "Vision", "Tool", "Fallback"]) {
      expect(html).toContain(role)
    }
    expect(html).not.toContain("Token")
    expect(html).not.toContain("温度")
  })
})
