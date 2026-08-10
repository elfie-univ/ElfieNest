import { fireEvent, render, screen, waitFor } from "@testing-library/react"
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
  display_name: "阿尔法",
  gender: "male",
  birth_date: "1990-02-03",
  role: "owner",
  theme_key: "warm-paper",
  user_id: 1,
} satisfies ClientUser

const admin = {
  ...owner,
  account_id: "admin01",
  display_name: "管理员",
  role: "admin",
} satisfies ClientUser

function renderLocalized(locale: SupportedLocale, panel = false, onLoggedOut?: () => void, user: ClientUser = owner): void {
  const instance = createI18n()
  initializeLocale(instance, {
    browserLanguages: [locale],
    documentElement: document.documentElement,
    storage: localStorage,
  })
  render(
    <I18nextProvider i18n={instance}>
      {panel
        ? <AccountMenuPanel onClose={() => undefined} onUpdated={async () => undefined} user={user} {...(onLoggedOut === undefined ? {} : { onLoggedOut })} />
        : <AccountMenu onUpdated={async () => undefined} user={user} />}
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
    renderLocalized("zh-CN")

    fireEvent.click(screen.getByRole("button", { name: /阿尔法/ }))
    fireEvent.click(screen.getByRole("button", { name: /默认登录页/ }))
    fireEvent.pointerDown(screen.getByRole("combobox", { name: "默认登录页" }), {
      button: 0,
      ctrlKey: false,
      pointerType: "mouse",
    })
    fireEvent.click(await screen.findByRole("option", { name: "聊天页" }))

    expect(screen.getByRole("region", { name: "个人与外观设置" })).toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: "默认登录页" })).toHaveTextContent("聊天页")
  }, 10_000)

  it("renders display-first identity information with only the local avatar upload control", () => {
    renderLocalized("zh-CN", true)

    expect(screen.getByText("阿尔法")).toBeInTheDocument()
    expect(screen.getByText("账号：")).toBeInTheDocument()
    expect(screen.getByText("admin123")).toBeInTheDocument()
    expect(screen.getByText("角色：")).toBeInTheDocument()
    expect(screen.getByText("出生日期：")).toBeInTheDocument()
    expect(screen.getByLabelText("男")).toBeInTheDocument()
    expect(screen.queryByText("个人设置")).not.toBeInTheDocument()
    expect(screen.getAllByLabelText("上传本地头像")).toHaveLength(2)
    expect(screen.queryByLabelText("显示名称")).not.toBeInTheDocument()
  })

  it("keeps the compact account trigger focused on the display name", () => {
    renderLocalized("zh-CN")

    const trigger = screen.getByRole("button", { name: "阿尔法" })

    expect(trigger.querySelector("strong")).toHaveTextContent("阿尔法")
    expect(trigger.querySelector("small")).toBeNull()
  })

  it("shows the Admin role only in the expanded panel and keeps the manager landing preference", async () => {
    const user = userEvent.setup()
    renderLocalized("en-US", false, undefined, admin)

    const trigger = screen.getByRole("button", { name: "管理员" })

    expect(trigger.querySelector("small")).toBeNull()
    await user.click(trigger)

    expect(screen.getAllByText("Admin")).toHaveLength(1)
    await user.click(screen.getByRole("button", { name: /Default landing page/ }))
    expect(screen.getByRole("button", { name: "Save default page" })).toBeInTheDocument()
  })

  it("keeps logout as the final account action", async () => {
    // Given: the account menu is open for the current owner.
    const user = userEvent.setup()
    renderLocalized("zh-CN")
    await user.click(screen.getByRole("button", { name: /阿尔法/ }))

    // When: the menu actions are inspected.
    const panel = screen.getByRole("region", { name: "个人与外观设置" })
    const logoutButton = screen.getByRole("button", { name: "退出登录" })

    // Then: logout is visually separated and placed after every preference row.
    expect(logoutButton.closest(".account-menu__session")).not.toBeNull()
    expect(panel.lastElementChild).toContainElement(logoutButton)
  })

  it("revokes the current session before returning to login", async () => {
    // Given: logout succeeds before the browser is returned to the login page.
    const user = userEvent.setup()
    const onLoggedOut = vi.fn()
    kyMock.mockResolvedValue(new Response("{}", {
      headers: { "Content-Type": "application/json" },
      status: 200,
    }))
    renderLocalized("zh-CN", true, onLoggedOut)

    // When: the final session action is activated.
    await user.click(screen.getByRole("button", { name: "退出登录" }))

    // Then: the authenticated session is revoked through the canonical endpoint.
    await waitFor(() => expect(kyMock).toHaveBeenCalledWith("/api/v1/auth/logout", expect.objectContaining({ method: "POST" })))
    expect(onLoggedOut).toHaveBeenCalledOnce()
  })

  it("edits the complete identity projection after a second confirmation", async () => {
    // Given: the canonical profile editor is open for one account.
    const user = userEvent.setup()
    kyMock.mockResolvedValue(new Response(JSON.stringify({}), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    }))
    renderLocalized("en-US", true)
    await user.click(screen.getByRole("button", { name: "Edit display name" }))
    expect(document.querySelector(".account-menu__edit")).not.toBeInTheDocument()
    expect(screen.getByText("Birth date:")).toHaveClass("account-menu__identity-edit-label")

    // When: the identity fields are changed and the confirmation is accepted.
    const input = screen.getByRole("textbox", { name: "Edit display name" })
    await user.clear(input)
    await user.type(input, "Owner Renamed")
    const accountInput = screen.getByRole("textbox", { name: "Account:" })
    await user.clear(accountInput)
    await user.type(accountInput, "owner-renamed")
    const gender = screen.getByRole("combobox", { name: "Gender" })
    expect(gender).toHaveAttribute("data-slot", "select-trigger")
    await user.click(gender)
    await user.click(await screen.findByRole("option", { name: "Female" }))
    const birthDateInput = screen.getByLabelText("Birth date:")
    await user.clear(birthDateInput)
    await user.type(birthDateInput, "2000-01-02")
    await user.click(screen.getByRole("button", { name: "Save profile" }))
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Confirm profile changes")
    await user.click(screen.getByRole("button", { name: "Confirm" }))

    // Then: the request uses all editable identity fields.
    expect(kyMock).toHaveBeenCalledOnce()
    const request = kyMock.mock.calls[0]
    expect(request?.[0]).toBe("/api/v1/me/profile")
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      account_id: "owner-renamed",
      birth_date: "2000-01-02",
      display_name: "Owner Renamed",
      gender: "female",
    })
  }, 10_000)

  it("keeps the role read-only and closes a directly mounted panel from outside clicks", async () => {
    const onClose = vi.fn()
    const instance = createI18n()
    initializeLocale(instance, {
      browserLanguages: ["zh-CN"],
      documentElement: document.documentElement,
      storage: localStorage,
    })
    render(<I18nextProvider i18n={instance}><AccountMenuPanel onClose={onClose} onUpdated={async () => undefined} user={owner} /></I18nextProvider>)

    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "编辑显示名称" }))
    expect(screen.getByRole("textbox", { name: "角色：" })).toHaveAttribute("readonly")

    fireEvent.mouseDown(document.body)
    expect(onClose).toHaveBeenCalledOnce()
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
    expect(request?.[0]).toBe("/api/v1/me/theme")
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
