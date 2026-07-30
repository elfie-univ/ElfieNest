import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

import type { ClientUser } from "../api/client"
import { createI18n } from "../i18n/config"
import { initializeLocale, type SupportedLocale } from "../i18n/locale"
import { AccountMenu, AccountMenuPanel } from "./AccountMenu"

const kyMock = vi.hoisted(() => vi.fn())
vi.mock("ky", () => ({ default: kyMock }))

const owner = {
  account_id: "admin123",
  avatar_color: 2,
  avatar_kind: "initials",
  csrf_token: "test-token",
  default_landing_page: "manage",
  nickname: "阿尔法",
  role: "owner",
  theme_key: "warm-paper",
  username: "admin123",
} satisfies ClientUser

function renderLocalized(locale: SupportedLocale, panel = false): void {
  const instance = createI18n()
  initializeLocale(instance, {
    browserLanguages: [locale],
    documentElement: document.documentElement,
    storage: localStorage,
  })
  render(
    <I18nextProvider i18n={instance}>
      {panel
        ? <AccountMenuPanel onClose={() => undefined} onUpdated={async () => undefined} user={owner} />
        : <AccountMenu onUpdated={async () => undefined} user={owner} />}
    </I18nextProvider>,
  )
}

describe("AccountMenu", () => {
  beforeAll(() => {
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    kyMock.mockReset()
    localStorage.clear()
  })

  it("keeps the account panel open while choosing a portal-rendered landing page", async () => {
    const user = userEvent.setup()
    renderLocalized("zh-CN")

    await user.click(screen.getByRole("button", { name: /阿尔法/ }))
    await user.click(screen.getByRole("button", { name: /默认登录页/ }))
    await user.click(screen.getByRole("combobox", { name: "默认登录页" }))
    await user.click(await screen.findByRole("option", { name: "聊天页" }))

    expect(screen.getByRole("region", { name: "个人与外观设置" })).toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: "默认登录页" })).toHaveTextContent("聊天页")
  })

  it("renders display-first identity information with only the local avatar upload control", () => {
    renderLocalized("zh-CN", true)

    expect(screen.getByText("阿尔法")).toBeInTheDocument()
    expect(screen.getByText("@admin123")).toBeInTheDocument()
    expect(screen.getAllByLabelText("上传本地头像")).toHaveLength(2)
    expect(screen.queryByLabelText("显示名称")).not.toBeInTheDocument()
  })

  it("uses a primary action for saving the default landing page", async () => {
    const user = userEvent.setup()
    renderLocalized("zh-CN", true)

    await user.click(screen.getByRole("button", { name: /默认登录页/ }))

    const saveButton = screen.getByRole("button", { name: "保存默认页" })
    expect(saveButton).toHaveClass("account-menu__landing-action")
    expect(saveButton).toHaveAttribute("data-variant", "default")
  })

  it("keeps language collapsed as a Globe setting below the theme row", () => {
    // Given: profile settings open in Chinese.
    renderLocalized("zh-CN", true)

    // When: the collapsed settings are inspected before any interaction.
    const languageToggle = screen.getByRole("button", { name: /语言/ })
    const themeToggle = screen.getByRole("button", { name: /系统配色/ })

    // Then: language follows the same disclosure pattern and carries its Globe icon.
    expect(languageToggle).toHaveAttribute("aria-expanded", "false")
    expect(languageToggle.compareDocumentPosition(themeToggle) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy()
    expect(languageToggle.querySelector("svg.lucide-earth")).not.toBeNull()
    expect(screen.queryByRole("combobox", { name: "语言" })).not.toBeInTheDocument()
  })

  it("switches the open menu locally through its language disclosure without saving an account locale", async () => {
    const user = userEvent.setup()
    window.history.replaceState({ source: "account" }, "", "/manage?section=users")
    const initialUrl = window.location.href
    renderLocalized("zh-CN")
    await user.click(screen.getByRole("button", { name: /阿尔法/ }))
    await user.click(screen.getByRole("button", { name: /系统配色/ }))
    await user.click(screen.getByRole("button", { name: /语言/ }))

    await user.click(screen.getByRole("combobox", { name: "语言" }))
    await user.click(screen.getByRole("option", { name: "English" }))

    expect(screen.getByRole("region", { name: "Profile and appearance settings" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Language/ })).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByRole("button", { name: /Color theme/ })).toHaveAttribute("aria-expanded", "false")
    expect(window.location.href).toBe(initialUrl)
    expect(kyMock).not.toHaveBeenCalled()
  })

  it("hides backend detail when saving an English theme fails", async () => {
    const user = userEvent.setup()
    kyMock.mockResolvedValue(new Response(
      JSON.stringify({ detail: "后端配色保存失败" }),
      { headers: { "Content-Type": "application/json" }, status: 500 },
    ))
    renderLocalized("en-US", true)

    await user.click(screen.getByRole("button", { name: /Color theme/ }))
    await user.click(screen.getByRole("button", { name: /Harbor Blue/ }))

    expect(kyMock).toHaveBeenCalledOnce()
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to save management data.")
    expect(screen.getByRole("alert")).not.toHaveTextContent("后端配色保存失败")
    const request = kyMock.mock.calls[0]
    expect(request?.[0]).toBe("/api/auth/me/theme")
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({ theme_key: "harbor-blue" })
  })

  it("switches language from the disclosure after a Chinese theme error", async () => {
    const user = userEvent.setup()
    kyMock.mockResolvedValue(new Response(
      JSON.stringify({ detail: "后端配色详情" }),
      { headers: { "Content-Type": "application/json" }, status: 500 },
    ))
    renderLocalized("zh-CN", true)

    await user.click(screen.getByRole("button", { name: /系统配色/ }))
    await user.click(screen.getByRole("button", { name: /港湾蓝/ }))
    expect(await screen.findByRole("alert")).toHaveTextContent("后端配色详情")
    await user.click(screen.getByRole("button", { name: /语言/ }))
    await user.click(screen.getByRole("combobox", { name: "语言" }))
    await user.click(screen.getByRole("option", { name: "English" }))

    expect(screen.getByRole("button", { name: /Language/ })).toHaveAttribute("aria-expanded", "true")
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })
})
