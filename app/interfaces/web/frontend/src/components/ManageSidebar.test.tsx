import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import type { ClientUser } from "../api/client"
import type { ManageTab } from "../pages/manageNavigation"
import { MANAGE_NAV_GROUPS } from "../pages/manageNavigation"
import { ManageSidebar } from "./ManageSidebar"

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

function renderSidebar(activeTab: ManageTab = "users") {
  const onSelect = vi.fn()
  render(<ManageSidebar activeTab={activeTab} onSelect={onSelect} onUserUpdated={async () => undefined} user={owner} />)
  return { onSelect }
}

describe("ManageSidebar", () => {
  it("keeps accessible navigation labels and active route behavior", async () => {
    const user = userEvent.setup()
    const { onSelect } = renderSidebar("users")
    const navigation = screen.getByRole("navigation")
    const navButtons = within(navigation).getAllByRole("button")
    const expectedLabels = MANAGE_NAV_GROUPS.flatMap((group) => group.items.map((item) => item.label))

    expect(navButtons.map((button) => button.textContent)).toEqual(expectedLabels)
    expect(within(navigation).getByRole("button", { name: "用户管理" })).toHaveAttribute("aria-current", "page")
    expect(within(navigation).getByRole("button", { name: "状态监控" })).not.toHaveAttribute("aria-current")

    await user.click(within(navigation).getByRole("button", { name: "模型订阅" }))

    expect(onSelect).toHaveBeenCalledWith("providers")
  })

  it("renders one visible brand without the owner-console subtitle", () => {
    renderSidebar("users")
    const sidebar = screen.getByLabelText("ElfieNest 管理导航")

    expect(within(sidebar).getAllByText("ELFIE NEST")).toHaveLength(1)
    expect(within(sidebar).queryByText(/管理系统|OWNER CONSOLE/)).not.toBeInTheDocument()
  })

  it("labels navigation groups as accessible groups around their actions", () => {
    renderSidebar("monitor")
    const navigation = screen.getByRole("navigation")

    for (const group of MANAGE_NAV_GROUPS) {
      const renderedGroup = within(navigation).getByRole("group", { name: group.label })

      expect(within(renderedGroup).getAllByRole("button").map((button) => button.textContent)).toEqual(
        group.items.map((item) => item.label),
      )
    }
  })

  it("exposes quick entries and account controls as accessible sidebar actions", async () => {
    const user = userEvent.setup()
    renderSidebar("users")
    const chatLink = screen.getByRole("link", { name: "进入聊天" })
    const mobileAccessButton = screen.getByRole("button", { name: "用手机打开管理台" })
    const accountTrigger = screen.getByRole("button", { name: /阿尔法/ })

    expect(chatLink).toHaveAttribute("href", "/chat")
    expect(mobileAccessButton).toHaveAttribute("type", "button")
    expect(accountTrigger).toHaveAttribute("aria-haspopup", "dialog")
    expect(accountTrigger).toHaveAttribute("aria-expanded", "false")

    await user.click(accountTrigger)

    expect(screen.getByLabelText("个人与外观设置")).toBeInTheDocument()
    expect(accountTrigger).toHaveAttribute("aria-expanded", "true")
  })

  it("opens the mobile management access dialog from the sidebar action", async () => {
    const user = userEvent.setup()
    renderSidebar("users")

    await user.click(screen.getByRole("button", { name: "用手机打开管理台" }))

    const dialog = screen.getByRole("dialog", { name: "用手机打开 ElfieNest" })
    expect(within(dialog).getByRole("button", { name: "关闭手机访问二维码" })).toBeInTheDocument()
  })
})
