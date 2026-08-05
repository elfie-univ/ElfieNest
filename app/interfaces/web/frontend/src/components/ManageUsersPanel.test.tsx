import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

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
const admin: OwnerUser = {
  ...member,
  user_id: 2,
  account_id: "admin02",
  display_name: "Admin",
  role: "admin",
  avatar_url: null,
}

function renderPanel(locale: SupportedLocale = "zh-CN", actorRole: "owner" | "admin" = "owner") {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  document.documentElement.lang = locale
  return {
    instance,
    ...render(<I18nextProvider i18n={instance}><ManageUsersPanel actorRole={actorRole} csrfToken="csrf" /></I18nextProvider>),
  }
}

function cardForAccount(cards: readonly HTMLElement[], accountId: string): HTMLElement | undefined {
  return cards.find((card) => card.querySelectorAll(".user-id-card__identity > div dd")[2]?.textContent === accountId)
}

function accountIdForCard(card: HTMLElement): string | undefined {
  return card.querySelectorAll(".user-id-card__identity > div dd")[2]?.textContent ?? undefined
}

describe("ManageUsersPanel real-data states", () => {
  beforeAll(() => {
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
  })

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(ownerUsers).mockResolvedValue([owner, member])
    vi.mocked(createManagedUser).mockResolvedValue(member)
    vi.mocked(resetManagedUserPassword).mockResolvedValue({ temporary_password: "Temp12345678" })
    vi.mocked(deleteManagedUser).mockResolvedValue()
    vi.mocked(updateManagedUser).mockResolvedValue(member)
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

  it("renders canonical values and hides only the Owner self action row", async () => {
    // Given/When: canonical Owner and member records load.
    renderPanel()
    const cards = await screen.findAllByRole("article")

    // Then: fallback name and final fields render without aliases or invented values.
    const memberCard = cards.find((card) => within(card).queryAllByText("member01").length > 0)
    if (!(memberCard instanceof HTMLElement)) throw new TypeError("Expected member card")
    expect([...memberCard.querySelectorAll(".user-id-card__identity dt")].map((field) => field.textContent)).toEqual([
      "姓名",
      "性别",
      "账号",
      "角色",
      "加入时间",
      "最近在线",
      "精灵数",
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
    expect(within(ownerCard).queryByRole("button")).not.toBeInTheDocument()
    expect(ownerCard.querySelector(".user-id-card__actions")).not.toBeInTheDocument()
    const memberActions = memberCard.querySelector(".user-id-card__actions")
    if (!(memberActions instanceof HTMLElement)) throw new TypeError("Expected member actions")
    for (const name of ["编辑 member01", "重置密码 member01", "删除用户 member01"]) {
      expect(within(memberActions).getByRole("button", { name })).toBeEnabled()
    }
  })

  it("exposes the responsive panel and four-plus-four identity groups", async () => {
    // Given: the canonical user records are loaded.
    renderPanel()

    // When: the management panel and first user card are located.
    const cards = await screen.findAllByRole("article")
    const panel = document.querySelector(".manage-identity-panel")
    const card = cards[0]
    if (!(panel instanceof HTMLElement) || !(card instanceof HTMLElement)) throw new TypeError("Expected user panel and card")
    expect(screen.queryByRole("heading", { name: "本地成员" })).not.toBeInTheDocument()

    // Then: layout CSS has stable anchors for the panel and two four-field groups.
    expect(panel).toHaveClass("manage-identity-panel")
    expect(card.querySelector(".identity-card__layout")).toBeInTheDocument()
    expect(card.querySelectorAll(".identity-card__primary > div")).toHaveLength(4)
    expect(card.querySelectorAll(".identity-card__secondary > div")).toHaveLength(4)
  })

  it("orders cards by role and then ascending numeric user ID", async () => {
    // Given: the API returns records in an arbitrary order, including two Users.
    vi.mocked(ownerUsers).mockResolvedValue([
      member,
      admin,
      { ...member, user_id: 3, account_id: "member03" },
      owner,
    ])

    // When: the user list renders.
    renderPanel()
    const cards = await screen.findAllByRole("article")

    // Then: role groups are fixed and IDs are ascending within each group.
    expect(cards.map(accountIdForCard)).toEqual(["owner01", "admin02", "member03", "member01"])
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
      expect(createManagedUser).toHaveBeenCalledWith("member02", "Member Two", "secret", "user", "csrf")
    })
  })

  it("edits only the Elfie limit and uses a numeric user ID", async () => {
    // Given: a member card is loaded.
    const user = userEvent.setup()
    renderPanel()

    // When: the limit editor is opened and the new limit is saved.
    await user.click(await screen.findByRole("button", { name: "编辑 member01" }))
    const quota = screen.getByRole("spinbutton", { name: "精灵上限" })
    await user.clear(quota)
    await user.type(quota, "6")
    await user.click(screen.getByRole("button", { name: "保存 member01" }))

    // Then: only the quota mutation crosses the backend boundary.
    await waitFor(() => expect(updateManagedUser).toHaveBeenCalledWith(7, { elfie_quota_override: 6 }, "csrf"))
    expect(deleteManagedUser).not.toHaveBeenCalled()
  })

  it("lets an Owner create an Admin and keeps an Admin actor read-only for peer cards", async () => {
    const user = userEvent.setup()
    vi.mocked(ownerUsers).mockResolvedValue([owner, admin, member])
    const ownerPanel = renderPanel("zh-CN", "owner")

    await user.click(await screen.findByRole("button", { name: "添加用户" }))
    await user.click(screen.getByRole("combobox", { name: "角色" }))
    await user.click(screen.getByRole("option", { name: "管理员" }))
    expect(screen.getByRole("combobox", { name: "角色" })).toHaveTextContent("管理员")

    await user.click(screen.getByRole("button", { name: "取消" }))
    ownerPanel.unmount()
    renderPanel("zh-CN", "admin")
    const cards = await screen.findAllByRole("article")
    const adminCard = cardForAccount(cards, "admin02")
    if (!(adminCard instanceof HTMLElement)) throw new TypeError("Expected Admin card")
    expect(within(adminCard).queryByRole("button")).not.toBeInTheDocument()
    const memberCard = cardForAccount(cards, "member01")
    if (!(memberCard instanceof HTMLElement)) throw new TypeError("Expected member card")
    for (const name of ["编辑 member01", "重置密码 member01", "删除用户 member01"]) {
      expect(within(memberCard).getByRole("button", { name })).toBeEnabled()
    }
  })

  it("hides the entire action row for an Admin actor on Owner and peer Admin cards", async () => {
    const user = userEvent.setup()
    vi.mocked(ownerUsers).mockResolvedValue([owner, admin, member])
    renderPanel("zh-CN", "admin")

    const cards = await screen.findAllByRole("article")
    for (const accountId of ["owner01", "admin02"]) {
      const card = cardForAccount(cards, accountId)
      if (!(card instanceof HTMLElement)) throw new TypeError(`Expected ${accountId} card`)
      expect(card.querySelector(".user-id-card__actions")).not.toBeInTheDocument()
    }
    const memberCard = cardForAccount(cards, "member01")
    if (!(memberCard instanceof HTMLElement)) throw new TypeError("Expected member card")
    for (const name of ["编辑 member01", "重置密码 member01", "删除用户 member01"]) {
      expect(within(memberCard).getByRole("button", { name })).toBeEnabled()
    }
  })

  it("filters the member cards by role without refetching or changing the loaded records", async () => {
    // Given: the loaded member list contains one account for each role.
    const user = userEvent.setup()
    vi.mocked(ownerUsers).mockResolvedValue([owner, admin, member])
    renderPanel()

    // When: the shared management filter is changed to Admin.
    await user.click(await screen.findByRole("combobox", { name: "角色" }))
    await user.click(screen.getByRole("option", { name: "管理员" }))

    // Then: only the selected role remains visible and the backend list is not reloaded.
    expect(await screen.findAllByRole("article")).toHaveLength(1)
    expect(screen.getByText("admin02")).toBeInTheDocument()
    expect(screen.queryByText("owner01")).not.toBeInTheDocument()
    expect(screen.queryByText("member01")).not.toBeInTheDocument()
    expect(ownerUsers).toHaveBeenCalledTimes(1)
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

  it("places the create form inside the shared dialog fields container", async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.click(await screen.findByRole("button", { name: "添加用户" }))
    const form = screen.getByRole("dialog", { name: "添加本地用户" }).querySelector("form")
    if (!(form instanceof HTMLFormElement)) throw new TypeError("Expected create form")
    expect(form).toHaveClass("manage-dialog__form")
    expect(form.parentElement).toHaveClass("manage-dialog__fields")
  })
})
