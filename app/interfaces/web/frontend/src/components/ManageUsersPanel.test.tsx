import { act, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError, deleteManagedUser, ownerUsers, resetManagedUserPassword, updateManagedUser } from "../api/client"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
import { ManageUsersPanel } from "./ManageUsersPanel"

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return {
    ...original,
    deleteManagedUser: vi.fn(),
    ownerUsers: vi.fn(),
    resetManagedUserPassword: vi.fn(),
    updateManagedUser: vi.fn(),
  }
})

const alice = {
  account_id: "alice",
  username: "alice",
  display_name: "Alice",
  role: "user" as const,
  created_at: "2026-07-26T00:00:00Z",
  gender: null,
  birth_date: null,
  elfie_count: 1,
  elfie_quota_override: null,
  effective_elfie_limit: 3,
  online_status: "offline" as const,
  avatar_url: null,
}
const bob = {
  ...alice,
  account_id: "bob",
  username: "bob",
  display_name: "Bob",
  elfie_count: 0,
  elfie_quota_override: 5,
  effective_elfie_limit: 5,
}
const owner = {
  ...alice,
  account_id: "owner",
  username: "owner",
  display_name: "Owner",
  role: "owner" as const,
  elfie_count: 0,
  effective_elfie_limit: 9,
  online_status: "online" as const,
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

describe("ManageUsersPanel", () => {
  beforeEach(() => {
    vi.mocked(ownerUsers).mockResolvedValue([owner, alice, bob])
    vi.mocked(resetManagedUserPassword).mockResolvedValue()
    vi.mocked(updateManagedUser).mockResolvedValue(bob)
    vi.mocked(deleteManagedUser).mockResolvedValue()
  })

  it("renders identity cards with exact fields and protected removal", async () => {
    const user = userEvent.setup()
    renderPanel()

    const cards = await screen.findAllByRole("article")
    expect(cards).toHaveLength(3)
    const ownerCard = cards.find((card) => within(card).queryByText("@owner"))
    if (!(ownerCard instanceof HTMLElement)) throw new TypeError("Expected Owner card")
    expect(within(ownerCard).getByText("在线")).toBeInTheDocument()
    expect(within(ownerCard).getAllByRole("term").map((node) => node.textContent)).toEqual([
      "姓名",
      "性别",
      "登录账号",
      "出生日期",
      "当前角色",
      "加入时间",
      "当前精灵数",
      "精灵上限",
    ])
    expect(within(ownerCard).getByText("@owner")).toBeInTheDocument()
    expect(screen.queryByText("上限来源")).not.toBeInTheDocument()
    expect(screen.queryByText("成员 ID")).not.toBeInTheDocument()
    const protectedRemove = within(ownerCard).getByRole("button", { name: "删除用户 owner" })
    expect(protectedRemove).toBeDisabled()
    await user.click(protectedRemove)
    expect(vi.mocked(deleteManagedUser)).not.toHaveBeenCalled()
  })

  it("edits only the adoption limit inline and supports cancel", async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.click(await screen.findByRole("button", { name: "编辑 alice" }))
    expect(screen.queryByRole("dialog", { name: "编辑领养上限" })).not.toBeInTheDocument()
    const limit = screen.getByRole("spinbutton", { name: "精灵上限" })
    expect(screen.queryByRole("textbox", { name: "姓名" })).not.toBeInTheDocument()
    expect(screen.queryByRole("textbox", { name: "登录账号" })).not.toBeInTheDocument()

    await user.clear(limit)
    await user.type(limit, "7")
    await user.click(screen.getByRole("button", { name: "取消 alice" }))
    expect(screen.queryByRole("textbox", { name: "精灵上限" })).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "编辑 alice" }))
    await user.clear(screen.getByRole("spinbutton", { name: "精灵上限" }))
    await user.type(screen.getByRole("spinbutton", { name: "精灵上限" }), "7")
    await user.click(screen.getByRole("button", { name: "保存 alice" }))

    expect(vi.mocked(updateManagedUser)).toHaveBeenCalledWith("alice", { elfie_quota_override: 7 }, "csrf")
  })

  it("confirms reset password to 123456", async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.click(await screen.findByRole("button", { name: "重置密码 bob" }))
    await user.click(screen.getByRole("button", { name: "重置为 123456" }))

    expect(vi.mocked(resetManagedUserPassword)).toHaveBeenCalledWith("bob", "csrf")
  })

  it("uses the frontend demo cards when the legacy API returns no manageable members", async () => {
    vi.mocked(ownerUsers).mockResolvedValue([])

    renderPanel()

    expect(await screen.findByText("管理员")).toBeInTheDocument()
    expect(screen.getByText("后端暂不可用，当前显示演示数据")).toBeInTheDocument()
  })

  it("renders deterministic English member cards without translating entity values", async () => {
    // Given: the API returns members in a non-alphabetical order.
    vi.mocked(ownerUsers).mockResolvedValue([bob, owner, alice])

    // When: the member panel renders in English.
    renderPanel("en-US")

    // Then: localized chrome is English, cards are sorted, and IDs/names are unchanged.
    expect(await screen.findByRole("heading", { name: "Local members" })).toBeInTheDocument()
    const cards = screen.getAllByRole("article")
    expect(cards.map((card) => within(card).getAllByRole("definition")[0]?.textContent)).toEqual(["Alice", "Bob", "Owner"])
    expect(screen.getByText("@alice")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Delete user owner" })).toBeDisabled()
  })

  it("preserves the edited quota when locale changes mid-edit", async () => {
    // Given: Alice's adoption quota is being edited.
    const user = userEvent.setup()
    const { instance } = renderPanel()
    await user.click(await screen.findByRole("button", { name: "编辑 alice" }))
    const quota = screen.getByRole("spinbutton", { name: "精灵上限" })
    await user.clear(quota)
    await user.type(quota, "7")

    // When: the same mounted panel switches to English.
    await act(async () => { await instance.changeLanguage("en-US") })

    // Then: edit mode and the typed quota remain intact.
    expect(screen.getByRole("spinbutton", { name: "Elfie limit" })).toHaveValue(7)
    expect(screen.getByRole("button", { name: "Save alice" })).toBeInTheDocument()
  })

  it("uses a closed English fallback for backend detail and localizes invalid quota", async () => {
    // Given: loading exposes backend Chinese detail.
    vi.mocked(ownerUsers).mockRejectedValue(new ApiError(503, "后端成员读取失败"))

    // When: the panel loads in English and an invalid quota is submitted.
    const user = userEvent.setup()
    renderPanel("en-US")
    expect(await screen.findByRole("status")).toHaveTextContent("The backend is unavailable, so demo data is shown.")
    expect(screen.queryByText("后端成员读取失败")).not.toBeInTheDocument()
    vi.mocked(ownerUsers).mockResolvedValue([alice])
    await user.click(screen.getByRole("button", { name: "Refresh" }))
    await user.click(screen.getByRole("button", { name: "Edit alice" }))
    const quota = screen.getByRole("spinbutton", { name: "Elfie limit" })
    await user.clear(quota)
    await user.type(quota, "0")
    await user.click(screen.getByRole("button", { name: "Save alice" }))

    // Then: the local validation message is English.
    expect(screen.getByRole("alert")).toHaveTextContent("The Elfie limit must be an integer of at least 1.")
  })
})
