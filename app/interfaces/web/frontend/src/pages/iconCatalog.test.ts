import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { iconCatalog } from "./iconCatalog"
import { IconCatalogPage } from "./IconCatalogPage"

describe("iconCatalog", () => {
  it("keeps three visible choices for every desktop navigation function", () => {
    expect(iconCatalog).toHaveLength(14)
    expect(iconCatalog.every((group) => group.choices.length === 3)).toBe(true)
    expect(new Set(iconCatalog.map((group) => group.id)).size).toBe(iconCatalog.length)
  })

  it("renders each candidate as a real selection button instead of a layout-only wrapper", () => {
    const html = renderToStaticMarkup(createElement(IconCatalogPage))
    const choiceButtons = html.match(/class="icon-catalog-choice__select"/g) ?? []

    expect(choiceButtons).toHaveLength(iconCatalog.length * 3)
  })
})
