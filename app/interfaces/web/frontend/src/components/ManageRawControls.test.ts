import { readFileSync } from "node:fs"
import { resolve } from "node:path"

import { describe, expect, it } from "vitest"

const MANAGE_PANELS = [
  "OwnerNestPanel.tsx",
  "ManageUsersPanel.tsx",
  "OwnerProviderPanel.tsx",
  "OwnerFoodPanel.tsx",
  "SystemSettingsPanel.tsx",
] as const
const REACHABLE_MANAGE_SURFACES = [
  ...MANAGE_PANELS,
  "AccountMenu.tsx",
  "ManageMonitorPanel.tsx",
  "ManageSidebar.tsx",
  "OwnerElfieOverview.tsx",
] as const

describe("Manage raw browser controls", () => {
  it.each(MANAGE_PANELS)("does not use window.confirm in %s", (filename) => {
    const source = readFileSync(resolve(import.meta.dirname, filename), "utf8")

    expect(source).not.toContain("window.confirm")
  })

  it("routes the Nest numeric field and camera surface through shared controls", () => {
    const source = readFileSync(resolve(import.meta.dirname, "OwnerNestPanel.tsx"), "utf8")

    expect(source).not.toContain('type="number"')
    expect(source).not.toContain('aria-modal="true"')
  })

  it.each(["ManageUsersPanel.tsx", "OwnerProviderPanel.tsx"] as const)(
    "routes form fields and dialog shells through shared controls in %s",
    (filename) => {
      const source = readFileSync(resolve(import.meta.dirname, filename), "utf8")

      expect(source).not.toContain("<input")
      expect(source).not.toContain('aria-modal="true"')
    },
  )

  it("routes system settings through the shared numeric and checkbox controls", () => {
    const source = readFileSync(resolve(import.meta.dirname, "SystemSettingsPanel.tsx"), "utf8")

    expect(source).not.toContain('type="number"')
    expect(source).not.toContain('type="checkbox"')
    expect(source).toContain("<NumberField")
    expect(source).toContain("<CheckboxField")
  })

  it("keeps legacy JSON catalog panels outside the reachable manage page", () => {
    const managePage = readFileSync(resolve(import.meta.dirname, "../pages/ManagePage.tsx"), "utf8")

    expect(managePage).not.toContain("OwnerDataPanel")
    expect(managePage).not.toContain("OwnerRuntimeCatalogPanels")
    expect(managePage).not.toContain("RuntimeLogPanel")
  })

  it.each(REACHABLE_MANAGE_SURFACES)("does not expose raw JSON or browser-native Manage actions in %s", (filename) => {
    const source = readFileSync(resolve(import.meta.dirname, filename), "utf8")

    expect(source).not.toContain("window.confirm")
    expect(source).not.toContain("window.alert")
    expect(source).not.toContain("<pre")
    expect(source).not.toContain('type="number"')
    expect(source).not.toContain('type="checkbox"')
    expect(source).not.toMatch(/<select\b/)
  })
})
