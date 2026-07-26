import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { deleteManagedUser, ownerUsers, updateManagedUser } from "../api/client"
import { ManageUsersPanel } from "./ManageUsersPanel"

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return {
    ...original,
    deleteManagedUser: vi.fn(),
    ownerUsers: vi.fn(),
    updateManagedUser: vi.fn(),
  }
})

const alice = {
  id: 2,
  username: "alice",
  display_name: "Alice",
  role: "user" as const,
  created_at: "2026-07-26T00:00:00Z",
  elfie_count: 1,
  elfie_quota_override: null,
  effective_elfie_limit: 3,
  online_status: "unknown" as const,
  avatar_url: null,
}
const bob = {
  ...alice,
  id: 3,
  username: "bob",
  display_name: "Bob",
  elfie_count: 0,
  elfie_quota_override: 5,
  effective_elfie_limit: 5,
}

describe("ManageUsersPanel", () => {
  beforeEach(() => {
    vi.mocked(ownerUsers).mockResolvedValue([alice, bob])
    vi.mocked(updateManagedUser).mockResolvedValue(bob)
    vi.mocked(deleteManagedUser).mockResolvedValue()
  })

  it("renders identity cards with honest status and protected removal", async () => {
    const user = userEvent.setup()
    render(<ManageUsersPanel csrfToken="csrf" />)

    const cards = await screen.findAllByRole("article")
    expect(cards).toHaveLength(2)
    expect(within(cards[0]!).getByText("状态未知")).toBeInTheDocument()
    expect(within(cards[0]!).getByText("1 / 3")).toBeInTheDocument()
    const protectedRemove = within(cards[0]!).getByRole("button", { name: "移除 alice" })
    expect(protectedRemove).toBeDisabled()
    await user.click(protectedRemove)
    expect(vi.mocked(deleteManagedUser)).not.toHaveBeenCalled()
  })

  it("edits only the adoption limit and can restore the system default", async () => {
    const user = userEvent.setup()
    render(<ManageUsersPanel csrfToken="csrf" />)

    await user.click(await screen.findByRole("button", { name: "编辑 alice 的领养上限" }))
    const dialog = screen.getByRole("dialog", { name: "编辑领养上限" })
    expect(within(dialog).getByRole("textbox", { name: "领养上限" })).toBeInTheDocument()
    expect(within(dialog).getByRole("checkbox", { name: "沿用系统默认上限" })).toBeChecked()
    expect(within(dialog).queryByRole("textbox", { name: "用户名" })).not.toBeInTheDocument()
    expect(within(dialog).queryByLabelText(/密码/)).not.toBeInTheDocument()

    await user.click(within(dialog).getByRole("checkbox", { name: "沿用系统默认上限" }))
    await user.click(within(dialog).getByRole("button", { name: "增加领养上限" }))
    await user.click(within(dialog).getByRole("button", { name: "保存上限" }))

    expect(vi.mocked(updateManagedUser)).toHaveBeenCalledWith(2, { elfie_quota_override: 4 }, "csrf")
  })
})
