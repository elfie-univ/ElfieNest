import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  ApiError,
  createManagedUser,
  deleteManagedUser,
  ownerUsers,
  resetManagedUserPassword,
  updateManagedUser,
  type OwnerUser,
} from "../api/client"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
import { ManageUsersPanel } from "./ManageUsersPanel"

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return {
    ...original,
    createManagedUser: vi.fn(),
    deleteManagedUser: vi.fn(),
    ownerUsers: vi.fn(),
    resetManagedUserPassword: vi.fn(),
    updateManagedUser: vi.fn(),
  }
})

const member: OwnerUser = {
  user_id: 7,
  account_id: "member01",
  display_name: null,
  role: "user",
  gender: "female",
  birth_date: "2020-02-03",
  presence: "away",
  last_seen_at: "2026-08-01T08:00:00Z",
  language: "zh-CN",
  created_at: "2026-07-31T00:00:00Z",
  elfie_count: 0,
  elfie_quota_override: null,
  effective_elfie_limit: 3,
  avatar_url: "/api/owner/users/7/avatar",
}
const owner: OwnerUser = {
  ...member,
  user_id: 1,
  account_id: "owner01",
  display_name: "Owner",
  role: "owner",
  presence: "online",
  language: "en-US",
  avatar_url: null,
}

function renderPanel(locale: SupportedLocale = "zh-CN") {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  document.documentElement.lang = locale
  return {
    instance,
    ...render(<I18nextProvider i18n={instance}><ManageUsersPanel csrfToken="csrf" /></I18nextProvider>),
  }
}

describe("ManageUsersPanel real-data states", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(ownerUsers).mockResolvedValue([owner, member])
    vi.mocked(createManagedUser).mockResolvedValue(member)
    vi.mocked(updateManagedUser).mockResolvedValue(member)
    vi.mocked(resetManagedUserPassword).mockResolvedValue({ temporary_password: "Temp12345678" })
    vi.mocked(deleteManagedUser).mockResolvedValue()
  })

  it("shows loading and then a genuine empty state without demo cards", async () => {
    // Given: the request remains pending until the assertion, then resolves empty.
    let resolveUsers: ((users: readonly OwnerUser[]) => void) | undefined
    vi.mocked(ownerUsers).mockReturnValue(new Promise((resolve) => { resolveUsers = resolve }))

    // When: the panel first renders.
    renderPanel()

    // Then: loading is explicit and the empty state appears only after resolution.
    expect(screen.getByText("正在加载用户…")).toBeInTheDocument()
    expect(screen.queryByText("暂无成员。")).not.toBeInTheDocument()
    await act(async () => { resolveUsers?.([]) })
    expect(await screen.findByText("暂无成员。")).toBeInTheDocument()
    expect(screen.queryByText("管理员")).not.toBeInTheDocument()
  })

  it("renders canonical values and makes every Owner mutation read-only", async () => {
    // Given/When: canonical Owner and member records load.
    renderPanel()
    const cards = await screen.findAllByRole("article")

    // Then: fallback name and final fields render without aliases or invented values.
    const memberCard = cards.find((card) => within(card).queryAllByText("member01").length > 0)
    if (!(memberCard instanceof HTMLElement)) throw new TypeError("Expected member card")
    expect([...memberCard.querySelectorAll(".user-id-card__identity dt")].map((field) => field.textContent)).toEqual([
      "姓名",
      "性别",
      "登录账号",
      "当前角色",
      "加入时间",
      "最近在线",
      "当前精灵数",
      "精灵上限",
    ])
    expect(within(memberCard).getByText("暂离")).toBeInTheDocument()
    expect(within(memberCard).getByText("2026-08-01")).toBeInTheDocument()
    expect(within(memberCard).getByText("0")).toBeInTheDocument()
    expect(within(memberCard).getByText("3")).toBeInTheDocument()
    expect(within(memberCard).queryByText("2020-02-03")).not.toBeInTheDocument()
    expect(within(memberCard).queryByText("zh-CN")).not.toBeInTheDocument()
    expect(within(memberCard).queryByText("7")).not.toBeInTheDocument()
    const ownerCard = cards.find((card) => within(card).queryAllByText("Owner").length > 0)
    if (!(ownerCard instanceof HTMLElement)) throw new TypeError("Expected Owner card")
    for (const name of ["编辑 owner01", "重置密码 owner01", "删除用户 owner01"]) {
      expect(within(ownerCard).getByRole("button", { name })).toBeDisabled()
    }
    expect(within(ownerCard).getByText("Owner 账户只能在个人设置中管理。")).toBeInTheDocument()
  })

  it("creates a user with account ID, optional display name, and password", async () => {
    // Given: the create dialog is open.
    renderPanel()
    fireEvent.click(await screen.findByRole("button", { name: "添加用户" }))

    // When: all canonical create fields are submitted.
    fireEvent.change(screen.getByRole("textbox", { name: "登录账号" }), { target: { value: "member02" } })
    fireEvent.change(screen.getByRole("textbox", { name: "显示名称（可选）" }), { target: { value: "Member Two" } })
    const password = screen.getByRole("group", { name: "初始密码" }).querySelector("input")
    if (!(password instanceof HTMLInputElement)) throw new TypeError("Expected password input")
    fireEvent.change(password, { target: { value: "secret" } })
    const form = screen.getByRole("dialog", { name: "添加本地用户" }).querySelector("form")
    if (!(form instanceof HTMLFormElement)) throw new TypeError("Expected create form")
    fireEvent.submit(form)

    // Then: the API receives exactly those identity fields.
    await waitFor(() => {
      expect(createManagedUser).toHaveBeenCalledWith("member02", "Member Two", "secret", "csrf")
    })
  })

  it("uses a numeric user ID for quota and delete mutations", async () => {
    // Given: a member card is loaded.
    const user = userEvent.setup()
    renderPanel()

    // When: quota is saved and deletion is confirmed.
    await user.click(await screen.findByRole("button", { name: "编辑 member01" }))
    const quota = screen.getByRole("spinbutton", { name: "精灵上限" })
    await user.clear(quota)
    await user.type(quota, "6")
    await user.click(screen.getByRole("button", { name: "保存 member01" }))
    await user.click(await screen.findByRole("button", { name: "删除用户 member01" }))
    await user.click(screen.getByRole("button", { name: "确认移除" }))

    // Then: both mutations receive the backend numeric identity.
    expect(updateManagedUser).toHaveBeenCalledWith(7, { elfie_quota_override: 6 }, "csrf")
    expect(deleteManagedUser).toHaveBeenCalledWith(7, "csrf")
  })

  it("shows, copies, and clears a temporary password after reset", async () => {
    // Given: clipboard writing succeeds.
    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } })
    renderPanel()

    // When: reset completes and the result is copied.
    await user.click(await screen.findByRole("button", { name: "重置密码 member01" }))
    await user.click(screen.getByRole("button", { name: "确认重置" }))
    expect(await screen.findByText("Temp12345678")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "复制临时密码" }))

    // Then: copy is localized and closing removes plaintext from the DOM.
    expect(resetManagedUserPassword).toHaveBeenCalledWith(7, "csrf")
    expect(writeText).toHaveBeenCalledWith("Temp12345678")
    expect(screen.getByText("临时密码已复制。")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "关闭" }))
    expect(screen.queryByText("Temp12345678")).not.toBeInTheDocument()
  })

  it("localizes load and clipboard failures without exposing demo data", async () => {
    // Given: loading fails in English.
    vi.mocked(ownerUsers).mockRejectedValue(new ApiError(503, "后端成员读取失败"))
    const user = userEvent.setup()
    renderPanel("en-US")

    // When/Then: the error is localized and no records are invented.
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load users.")
    expect(screen.queryByRole("article")).not.toBeInTheDocument()

    // Given/When: data reloads, reset succeeds, but clipboard rejects.
    vi.mocked(ownerUsers).mockResolvedValue([member])
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new DOMException("denied")) },
    })
    await user.click(screen.getByRole("button", { name: "Refresh" }))
    await user.click(await screen.findByRole("button", { name: "Reset password member01" }))
    await user.click(screen.getByRole("button", { name: "Confirm reset" }))
    await user.click(await screen.findByRole("button", { name: "Copy temporary password" }))

    // Then: copy failure is localized and plaintext remains only in the open result dialog.
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to copy the temporary password.")
    expect(screen.getByText("Temp12345678")).toBeInTheDocument()
  })
})
