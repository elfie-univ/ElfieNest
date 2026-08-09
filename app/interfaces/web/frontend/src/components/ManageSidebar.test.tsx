import { act, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"

import { ApiError, type ClientUser } from "../api/client"
import { createI18n } from "../i18n/config"
import { initializeLocale, type SupportedLocale } from "../i18n/locale"
import type { ManageTab } from "../pages/manageNavigation"
import { MANAGE_NAV_GROUPS } from "../pages/manageNavigation"
import { ManageSidebar } from "./ManageSidebar"

const mobileAccessMock = vi.hoisted(() => vi.fn())

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return { ...original, mobileAccess: mobileAccessMock }
})

const owner = {
  account_id: "admin123",
  avatar_color: 2,
  avatar_kind: "initials",
  csrf_token: "test-token",
  default_landing_page: "manage",
  display_name: "阿尔法",
  role: "owner",
  theme_key: "warm-paper",
  user_id: 1,
} satisfies ClientUser

function renderSidebar(activeTab: ManageTab = "users", locale: SupportedLocale = "zh-CN") {
  const onSelect = vi.fn()
  const instance = createI18n()
  initializeLocale(instance, {
    browserLanguages: [locale],
    documentElement: document.documentElement,
    storage: localStorage,
  })
  render(<I18nextProvider i18n={instance}><ManageSidebar activeTab={activeTab} onSelect={onSelect} onUserUpdated={async () => undefined} user={owner} /></I18nextProvider>)
  return { instance, onSelect }
}

describe("ManageSidebar", () => {
  it("keeps accessible navigation labels and active route behavior", async () => {
    const user = userEvent.setup()
    const { onSelect } = renderSidebar("users")
    const navigation = screen.getByRole("navigation")
    const navButtons = within(navigation).getAllByRole("button")
    const expectedLabels = ["状态监控", "用户管理", "精灵管理", "精灵巢管理", "模型订阅", "粮食策略", "系统设置"]

    expect(navButtons.map((button) => button.textContent)).toEqual(expectedLabels)
    expect(within(navigation).getByRole("button", { name: "用户管理" })).toHaveAttribute("aria-current", "page")
    expect(within(navigation).getByRole("button", { name: "状态监控" })).not.toHaveAttribute("aria-current")

    await user.click(within(navigation).getByRole("button", { name: "模型订阅" }))

    expect(onSelect).toHaveBeenCalledWith("providers")
  })

  it("renders one full logo without the owner-console subtitle", () => {
    renderSidebar("users")
    const sidebar = screen.getByLabelText("ElfieNest 管理导航")

    expect(within(sidebar).getByRole("img", { name: "ELFIE NEST" })).toHaveAttribute(
      "src",
      expect.stringContaining("elfienest-full-logo-transparent.png"),
    )
    expect(within(sidebar).queryByText("ELFIE NEST")).not.toBeInTheDocument()
    expect(within(sidebar).queryByText(/管理系统|OWNER CONSOLE/)).not.toBeInTheDocument()
  })

  it("labels navigation groups as accessible groups around their actions", () => {
    renderSidebar("monitor")
    const navigation = screen.getByRole("navigation")

    const expectedGroups = [
      { id: "operations", label: "运行维护", labels: ["状态监控"] },
      { id: "business", label: "业务管理", labels: ["用户管理", "精灵管理", "精灵巢管理"] },
      { id: "models", label: "模型与粮食", labels: ["模型订阅", "粮食策略"] },
      { id: "system", label: "系统配置", labels: ["系统设置"] },
    ] as const
    expect(MANAGE_NAV_GROUPS.map((group) => group.id)).toEqual(expectedGroups.map((group) => group.id))
    for (const group of expectedGroups) {
      const renderedGroup = within(navigation).getByRole("group", { name: group.label })

      expect(within(renderedGroup).getAllByRole("button").map((button) => button.textContent)).toEqual(
        group.labels,
      )
    }
  })

  it("exposes quick entries and account controls as accessible sidebar actions", async () => {
    const user = userEvent.setup()
    renderSidebar("users")
    const quickActions = screen.getByLabelText("快捷入口")
    const monitorLink = screen.getByRole("link", { name: "进入监控" })
    const chatLink = screen.getByRole("link", { name: "进入聊天" })
    const mobileAccessButton = screen.getByRole("button", { name: "用手机打开管理台" })
    const accountTrigger = screen.getByRole("button", { name: /阿尔法/ })

    expect(monitorLink).toHaveAttribute("href", "/monitor")
    expect(monitorLink.querySelector("svg")).toHaveClass("lucide-cctv")
    expect(chatLink).toHaveAttribute("href", "/chat")
    expect(within(quickActions).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual(["/monitor", "/chat"])
    expect(mobileAccessButton).toHaveAttribute("type", "button")
    expect(accountTrigger).toHaveAttribute("aria-haspopup", "dialog")
    expect(accountTrigger).toHaveAttribute("aria-expanded", "false")

    await user.click(accountTrigger)

    expect(screen.getByLabelText("个人与外观设置")).toBeInTheDocument()
    expect(accountTrigger).toHaveAttribute("aria-expanded", "true")
  })

  it("renders long English navigation and opens a localized mobile access dialog", async () => {
    const user = userEvent.setup()
    mobileAccessMock.mockRejectedValueOnce(new ApiError(500, "后端中文详情"))
    const { instance } = renderSidebar("users", "zh-CN")

    await user.click(screen.getByRole("button", { name: "用手机打开管理台" }))
    expect(await screen.findByText("后端中文详情")).toBeInTheDocument()
    await act(async () => { await instance.changeLanguage("en-US") })

    const dialog = screen.getByRole("dialog", { name: "Open ElfieNest on your phone" })
    expect(screen.getByRole("button", { name: "Elfie Nest management" })).toBeInTheDocument()
    expect(screen.getByRole("group", { name: "Models & Food" })).toBeInTheDocument()
    expect(screen.getByRole("group", { name: "System configuration" })).toBeInTheDocument()
    expect(within(dialog).getByRole("button", { name: "Close mobile access QR code" })).toBeInTheDocument()
    expect(await within(dialog).findByText("Unable to load management data.")).toBeInTheDocument()
    expect(within(dialog).queryByText("后端中文详情")).not.toBeInTheDocument()
  })
})
