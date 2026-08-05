import { fireEvent, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

import * as client from "../api/client"
import { ApiError } from "../api/client"
import { createI18n } from "../i18n/config"
import { initializeLocale, type SupportedLocale } from "../i18n/locale"
import { LoginPage } from "./LoginPage"

function renderLogin(locale: SupportedLocale): void {
  const instance = createI18n()
  initializeLocale(instance, {
    storage: localStorage,
    browserLanguages: [locale],
    documentElement: document.documentElement,
  })
  render(
    <I18nextProvider i18n={instance}>
      <LoginPage />
    </I18nextProvider>,
  )
}

function getFieldInput(label: string): HTMLElement {
  return within(screen.getByRole("group", { name: label })).getByLabelText(label)
}

describe("localized login", () => {
  beforeAll(() => {
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("keeps the compact language switcher in the login frame instead of the card", () => {
    // Given: the login page is rendered in its default Chinese locale.
    renderLogin("zh-CN")

    // When: the persistent language control is located.
    const localeControl = screen.getByRole("region", { name: "语言" })

    // Then: it is outside the card and the card has no language field of its own.
    expect(localeControl).toContainElement(screen.getByRole("combobox", { name: "语言" }))
    expect(localeControl.closest(".login")).toBeNull()
    expect(document.querySelector(".login [data-language-switcher]")).toBeNull()
  })

  it("keeps the safe destination and live form state when switching to English", async () => {
    // Given: a filled Chinese login form is submitting to an allowed local page.
    const user = userEvent.setup()
    window.history.replaceState({ source: "login" }, "", "/login?next=/manage")
    const initialUrl = window.location.href
    const initialHistoryLength = window.history.length
    vi.spyOn(client, "login").mockReturnValue(new Promise<string>(() => undefined))
    renderLogin("zh-CN")
    fireEvent.change(getFieldInput("账号"), { target: { value: "  owner  " } })
    fireEvent.change(getFieldInput("密码"), { target: { value: "secret-pass" } })

    // When: submission starts and the shared switcher changes the live page to English.
    await user.click(screen.getByRole("button", { name: "登录" }))
    await user.click(screen.getByRole("combobox", { name: "语言" }))
    await user.click(screen.getByRole("option", { name: "English" }))

    // Then: localized DOM changes without losing values, pending state, URL, or safe next.
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Log in",
    )
    expect(getFieldInput("Account")).toHaveValue("  owner  ")
    expect(getFieldInput("Password")).toHaveValue("secret-pass")
    expect(screen.getByRole("button", { name: "Signing in…" })).toBeDisabled()
    expect(client.login).toHaveBeenCalledWith("owner", "secret-pass", "/manage")
    expect(window.location.href).toBe(initialUrl)
    expect(window.history.length).toBe(initialHistoryLength)
  })

  it("rejects a malformed next and hides backend detail in English", async () => {
    // Given: an external next target and a backend failure containing private detail.
    const user = userEvent.setup()
    window.history.replaceState(null, "", "/login?next=https://evil.example")
    const initialUrl = window.location.href
    vi.spyOn(client, "login").mockRejectedValue(
      new ApiError(401, "后端凭据详情不可公开"),
    )
    renderLogin("en-US")

    // When: the English form is submitted.
    fireEvent.change(getFieldInput("Account"), { target: { value: "owner" } })
    fireEvent.change(getFieldInput("Password"), { target: { value: "secret-pass" } })
    await user.click(screen.getByRole("button", { name: "Log in" }))

    // Then: only the closed local fallback is visible and navigation remains same-origin.
    expect(await screen.findByRole("alert")).toHaveTextContent("Sign-in failed. Try again.")
    expect(screen.getByRole("alert")).not.toHaveTextContent("后端凭据详情不可公开")
    expect(client.login).toHaveBeenCalledWith("owner", "secret-pass", "")
    expect(window.location.href).toBe(initialUrl)
    expect(window.location.origin).toBe("http://localhost:3000")
  })

  it("recomputes an existing backend error when switching from Chinese to English", async () => {
    const user = userEvent.setup()
    vi.spyOn(client, "login").mockRejectedValue(new ApiError(401, "后端登录详情"))
    renderLogin("zh-CN")
    fireEvent.change(getFieldInput("账号"), { target: { value: "owner" } })
    fireEvent.change(getFieldInput("密码"), { target: { value: "secret-pass" } })

    await user.click(screen.getByRole("button", { name: "登录" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("后端登录详情")
    await user.click(screen.getByRole("combobox", { name: "语言" }))
    await user.click(screen.getByRole("option", { name: "English" }))

    expect(screen.getByRole("alert")).toHaveTextContent("Sign-in failed. Try again.")
    expect(screen.getByRole("alert")).not.toHaveTextContent("后端登录详情")
  })

  it("shows only the compact login copy around the branded logo", () => {
    // Given: the login page is rendered in Chinese.
    renderLogin("zh-CN")

    // Then: the branded logo and concise login hierarchy are visible.
    expect(screen.getByRole("img", { name: "ELFIE NEST" })).toBeInTheDocument()
    expect(screen.getByText("ELFIE NEST")).toBeInTheDocument()
    expect(screen.getByText("ELFIENEST")).toBeInTheDocument()
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("登录")
    expect(screen.queryByText("回来吧，精灵正在等你。", { exact: true })).not.toBeInTheDocument()
    expect(screen.queryByText("登录后进入属于你的聊天与管理空间。", { exact: true })).not.toBeInTheDocument()
  })
})
