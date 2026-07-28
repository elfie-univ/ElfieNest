import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { deleteManagedUser, ownerUsers, resetManagedUserPassword, updateManagedUser } from "../api/client"
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

describe("ManageUsersPanel", () => {
  beforeEach(() => {
    vi.mocked(ownerUsers).mockResolvedValue([owner, alice, bob])
    vi.mocked(resetManagedUserPassword).mockResolvedValue()
    vi.mocked(updateManagedUser).mockResolvedValue(bob)
    vi.mocked(deleteManagedUser).mockResolvedValue()
  })

  it("renders identity cards with exact fields and protected removal", async () => {
    const user = userEvent.setup()
    render(<ManageUsersPanel csrfToken="csrf" />)

    const cards = await screen.findAllByRole("article")
    expect(cards).toHaveLength(3)
    expect(within(cards[0]!).getByText("在线")).toBeInTheDocument()
    expect(within(cards[0]!).getAllByRole("term").map((node) => node.textContent)).toEqual([
      "姓名",
      "性别",
      "登录账号",
      "出生日期",
      "当前角色",
      "加入时间",
      "当前精灵数",
      "精灵上限",
    ])
    expect(within(cards[0]!).getByText("@owner")).toBeInTheDocument()
    expect(screen.queryByText("上限来源")).not.toBeInTheDocument()
    expect(screen.queryByText("成员 ID")).not.toBeInTheDocument()
    const protectedRemove = within(cards[0]!).getByRole("button", { name: "删除用户 owner" })
    expect(protectedRemove).toBeDisabled()
    await user.click(protectedRemove)
    expect(vi.mocked(deleteManagedUser)).not.toHaveBeenCalled()
  })

  it("edits only the adoption limit inline and supports cancel", async () => {
    const user = userEvent.setup()
    render(<ManageUsersPanel csrfToken="csrf" />)

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
    render(<ManageUsersPanel csrfToken="csrf" />)

    await user.click(await screen.findByRole("button", { name: "重置密码 bob" }))
    await user.click(screen.getByRole("button", { name: "重置为 123456" }))

    expect(vi.mocked(resetManagedUserPassword)).toHaveBeenCalledWith("bob", "csrf")
  })
})
