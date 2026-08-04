import { createElement } from "react"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import { createI18n } from "../i18n/config"
import { initializeLocale, type SupportedLocale } from "../i18n/locale"
import { ManagePage } from "./ManagePage"

const session = vi.hoisted(() => ({
  loading: false,
  refresh: vi.fn(async () => undefined),
  user: {
    avatar_color: 2,
    avatar_kind: "initials" as const,
    csrf_token: "test-token",
    default_landing_page: "manage" as const,
    account_id: "admin123",
    display_name: "阿尔法",
    role: "owner" as "owner" | "admin",
    theme_key: "warm-paper" as const,
    user_id: 1,
  },
}))

vi.mock("../stores/session", () => ({
  useSession: () => ({ user: session.user, loading: session.loading, refresh: session.refresh }),
}))

vi.mock("../stores/heartbeat", () => ({
  usePresenceHeartbeat: () => undefined,
}))

vi.mock("../components/ManageMonitorPanel", () => ({ ManageMonitorPanel: () => "监控内容" }))
vi.mock("../components/ManageUsersPanel", () => ({ ManageUsersPanel: () => "用户内容" }))
vi.mock("../components/OwnerElfieOverview", () => ({ OwnerElfieOverview: () => "精灵内容" }))
vi.mock("../components/OwnerNestPanel", () => ({ OwnerNestPanel: () => "精灵巢内容" }))
vi.mock("../components/OwnerProviderPanel", () => ({ OwnerProviderPanel: () => "模型订阅内容" }))
vi.mock("../components/OwnerFoodPanel", () => ({ OwnerFoodPanel: () => "粮食内容" }))
vi.mock("../components/SystemSettingsPanel", () => ({ SystemSettingsPanel: () => "系统设置内容" }))
vi.mock("../components/ToolsPermissionsPanel", () => ({ ToolsPermissionsPanel: () => "工具与权限内容" }))
vi.mock("./IconCatalogPage", () => ({ IconCatalogPage: () => "图标目录" }))

function renderManagePage(section = "monitor", locale: SupportedLocale = "zh-CN"): void {
  window.history.replaceState({}, "", `/manage?section=${section}`)
  const instance = createI18n()
  initializeLocale(instance, {
    browserLanguages: [locale],
    documentElement: document.documentElement,
    storage: localStorage,
  })
  render(createElement(I18nextProvider, { i18n: instance }, createElement(ManagePage)))
}

describe("ManagePage", () => {
  beforeAll(() => {
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
  })

  beforeEach(() => {
    session.loading = false
    session.refresh.mockClear()
  })

  it("does not render the account default-login preference inside the monitor panel", () => {
    renderManagePage("monitor")

    expect(screen.getByRole("heading", { level: 1, name: "状态监控" })).toBeInTheDocument()
    expect(screen.queryByText("默认打开页面")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "保存默认页" })).not.toBeInTheDocument()
  })

  it("allows an Admin to render the management surface", () => {
    session.user.role = "admin"

    renderManagePage("monitor")

    expect(screen.getByRole("heading", { level: 1, name: "状态监控" })).toBeInTheDocument()
    expect(window.location.pathname).toBe("/manage")

    session.user.role = "owner"
  })

  it("renders one page title without the repeated eyebrow and fixed Owner subtitle", () => {
    renderManagePage("users")

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1)
    expect(screen.queryByText("管理、聊天与领养保持分离")).not.toBeInTheDocument()
  })

  it("renders the ElfieNest logo and single sidebar brand without the console subtitle", () => {
    renderManagePage("users")
    const sidebar = screen.getByLabelText("ElfieNest 管理导航")

    expect(within(sidebar).getByAltText("ElfieNest")).toBeInTheDocument()
    expect(within(sidebar).getAllByText("ELFIE NEST")).toHaveLength(1)
    expect(within(sidebar).queryByText(/管理系统|OWNER CONSOLE/)).not.toBeInTheDocument()
  })

  it("does not repeat active page titles inside reachable panel content", () => {
    renderManagePage("tools")

    expect(screen.getByRole("heading", { level: 1, name: "工具与权限" })).toBeInTheDocument()
    expect(screen.queryByRole("heading", { level: 2, name: "工具与权限" })).not.toBeInTheDocument()
  })

  it("keeps the mobile navigation compact enough for content to enter the first viewport", () => {
    // Given: the responsive Manage console stylesheet.
    const styles = readFileSync(resolve(import.meta.dirname, "../manage-console.css"), "utf8")
    const mobile = styles.slice(styles.indexOf("@media (max-width: 640px)"))

    // When: the narrow-screen navigation contract is inspected.
    const sidebarRule = mobile.match(/\.manage-sidebar\s*\{[^}]+\}/)?.[0] ?? ""
    const navigationRule = mobile.match(/\.manage-sidebar__navigation\s*\{[^}]+\}/)?.[0] ?? ""

    // Then: the rail releases viewport height and scrolls its items on one compact axis.
    expect(sidebarRule).toContain("height: auto")
    expect(navigationRule).toContain("display: flex")
    expect(navigationRule).toContain("overflow-x: auto")
  })

  it("places action-only management headers beside and below the title on desktop", () => {
    // Given: management page headers whose visible copy was intentionally removed.
    const styles = readFileSync(resolve(import.meta.dirname, "../manage-console.css"), "utf8")

    // When: the desktop management layout is loaded.
    const desktopHeader = styles.match(/\.manage--console \.manage-head\s*\{[^}]+\}/)?.[0] ?? ""
    const desktopActions = styles.match(/\.manage--console \.manage-head > \.manage-actions\s*\{[^}]+\}/)?.[0] ?? ""

    // Then: action-only headers leave the content flow and sit in the title row.
    expect(desktopHeader).toContain("position: absolute")
    expect(desktopHeader).toContain("top: 50px")
    expect(desktopHeader).toContain("inset-inline-end: 42px")
    expect(desktopActions).toContain("margin-top: 0")

    const tablet = styles.slice(styles.indexOf("@media (min-width: 641px) and (max-width: 860px)"))
    const tabletHeader = tablet.match(/\.manage--console \.manage-head\s*\{[^}]+\}/)?.[0] ?? ""
    expect(tabletHeader).toContain("top: 38px")

    // And: narrow layouts keep the existing stacked header flow.
    const mobile = styles.slice(styles.indexOf("@media (max-width: 640px)"))
    const mobileHeader = mobile.match(/\.manage--console \.manage-head\s*\{[^}]+\}/)?.[0] ?? ""
    expect(mobileHeader).toContain("position: static")
  })

  it("falls back from an unknown section to the localized monitor without rewriting the query", () => {
    renderManagePage("retired-section", "en-US")

    expect(screen.getByRole("heading", { level: 1, name: "Status monitor" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Status monitor" })).toHaveAttribute("aria-current", "page")
    expect(window.location.search).toBe("?section=retired-section")
  })

  it("switches the shell language without losing the active section or query", async () => {
    const user = userEvent.setup()
    renderManagePage("users")
    const originalUrl = window.location.href

    await user.click(screen.getByRole("button", { name: /阿尔法/ }))
    await user.click(screen.getByRole("button", { name: /语言/ }))
    await user.click(screen.getByRole("combobox", { name: "语言" }))
    await user.click(screen.getByRole("option", { name: "English" }))

    expect(screen.getByRole("heading", { level: 1, name: "User management" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "User management" })).toHaveAttribute("aria-current", "page")
    expect(window.location.href).toBe(originalUrl)
  })

  it("localizes the session verification state", () => {
    session.loading = true
    renderManagePage("monitor", "en-US")

    expect(screen.getByText("Verifying your session...")).toBeInTheDocument()
  })
})
