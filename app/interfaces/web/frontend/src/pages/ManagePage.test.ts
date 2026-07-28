import { createElement } from "react"
import { render, screen, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ManagePage } from "./ManagePage"

const session = vi.hoisted(() => ({
  refresh: vi.fn(async () => undefined),
  user: {
    avatar_color: 2,
    avatar_kind: "initials" as const,
    csrf_token: "test-token",
    default_landing_page: "manage" as const,
    account_id: "admin123",
    nickname: "阿尔法",
    role: "owner" as const,
    theme_key: "warm-paper" as const,
    username: "admin123",
  },
}))

vi.mock("../stores/session", () => ({
  useSession: () => ({ user: session.user, loading: false, refresh: session.refresh }),
}))

vi.mock("../stores/heartbeat", () => ({
  usePresenceHeartbeat: () => undefined,
}))

vi.mock("../components/ManageMonitorPanel", () => ({ ManageMonitorPanel: () => "监控内容" }))
vi.mock("../components/ManageUsersPanel", () => ({ ManageUsersPanel: () => "用户内容" }))
vi.mock("../components/OwnerElfieOverview", () => ({ OwnerElfieOverview: () => "精灵内容" }))
vi.mock("../components/OwnerNestPanel", () => ({ OwnerNestPanel: () => "精灵巢内容" }))
vi.mock("../components/OwnerProviderPanel", () => ({ OwnerProviderPanel: () => "模型订阅内容" }))
vi.mock("../components/OwnerFoodPanel", () => ({ OwnerFoodPanel: () => "粮食内容" }))
vi.mock("../components/SystemSettingsPanel", () => ({ SystemSettingsPanel: () => "系统设置内容" }))
vi.mock("./IconCatalogPage", () => ({ IconCatalogPage: () => "图标目录" }))

function renderManagePage(section = "monitor"): void {
  window.history.replaceState({}, "", `/manage?section=${section}`)
  render(createElement(ManagePage))
}

describe("ManagePage", () => {
  beforeEach(() => {
    session.refresh.mockClear()
  })

  it("does not render the account default-login preference inside the monitor panel", () => {
    renderManagePage("monitor")

    expect(screen.getByRole("heading", { level: 1, name: "状态监控" })).toBeInTheDocument()
    expect(screen.queryByText("默认打开页面")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "保存默认页" })).not.toBeInTheDocument()
  })

  it("renders one page title without the repeated eyebrow and fixed Owner subtitle", () => {
    renderManagePage("users")

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1)
    expect(screen.queryByText("管理、聊天与领养保持分离")).not.toBeInTheDocument()
  })

  it("renders the ElfieNest logo and single sidebar brand without the console subtitle", () => {
    renderManagePage("users")
    const sidebar = screen.getByLabelText("ElfieNest 管理导航")

    expect(within(sidebar).getByAltText("ElfieNest")).toBeInTheDocument()
    expect(within(sidebar).getAllByText("ELFIE NEST")).toHaveLength(1)
    expect(within(sidebar).queryByText(/管理系统|OWNER CONSOLE/)).not.toBeInTheDocument()
  })

  it("does not repeat active page titles inside reachable panel content", () => {
    renderManagePage("tools")

    expect(screen.getByRole("heading", { level: 1, name: "工具与权限" })).toBeInTheDocument()
    expect(screen.queryByRole("heading", { level: 2, name: "工具与权限" })).not.toBeInTheDocument()
  })
})
