import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { createI18n } from "../i18n/config"
import { ToolsPermissionsPanel } from "./ToolsPermissionsPanel"

const api = vi.hoisted(() => ({
  ownerRuntimeAudit: vi.fn(),
  ownerRuntimePolicy: vi.fn(),
  ownerRuntimeTools: vi.fn(),
  updateOwnerTool: vi.fn(),
  updateToolPermission: vi.fn(),
  verifyOwnerTool: vi.fn(),
}))

vi.mock("../api/owner-tools", () => api)

const webSearch = {
  enabled: true,
  provider: "duckduckgo",
  api_base: "",
  max_results: 3,
  max_result_bytes: 16000,
  timeout_seconds: 5,
  max_tool_calls: 3,
  max_total_result_bytes: 48000,
  has_api_key: false,
} as const

const localFile = {
  enabled: false,
  root: "",
  root_policy: "elfie_workspace",
  max_read_bytes: 65536,
  max_items: 200,
  max_result_bytes: 16000,
  max_tool_calls: 3,
  max_total_result_bytes: 48000,
  has_api_key: false,
} as const

const policy = {
  tool_permissions: {
    WEB_SEARCH: { mode: "allow", reason: "联网检索工具自动放行" },
    READ: { mode: "allow", reason: "只读工具自动放行" },
  },
} as const

function renderPanel(): void {
  const i18n = createI18n()
  render(<I18nextProvider i18n={i18n}><ToolsPermissionsPanel csrfToken="csrf-token" /></I18nextProvider>)
}

describe("ToolsPermissionsPanel", () => {
  beforeEach(() => {
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
  })

  beforeEach(() => {
    vi.clearAllMocks()
    api.ownerRuntimeTools.mockResolvedValue({ web_search: webSearch, local_file: localFile })
    api.ownerRuntimePolicy.mockResolvedValue(policy)
    api.ownerRuntimeAudit.mockResolvedValue({ event_count: 0, events: [] })
    api.updateOwnerTool.mockResolvedValue(webSearch)
    api.updateToolPermission.mockResolvedValue(policy)
  })

  it("renders the two real tools as independent settings rows", async () => {
    // Given: the existing runtime tools and permission projections are available.
    renderPanel()

    // When: the panel finishes its initial load.
    const search = await screen.findByRole("button", { name: "展开网络搜索详情" })

    // Then: both tools have separate disclosure buttons and main switches.
    expect(search).toHaveAttribute("aria-expanded", "false")
    expect(screen.getByRole("button", { name: "展开本地文件（只读）详情" })).toBeInTheDocument()
    expect(screen.getAllByText("展开配置")).toHaveLength(2)
    expect(document.querySelectorAll(".tool-settings-row__actions").item(0).textContent).toMatch(/工具已启用.*展开配置/)
    expect(document.querySelectorAll(".tool-settings-row__disclosure .lucide-chevron-down")).toHaveLength(2)
    const searchSwitch = screen.getByRole("switch", { name: "关闭网络搜索" })
    expect(searchSwitch).toHaveAttribute("aria-checked", "true")
    expect(searchSwitch.firstElementChild).not.toHaveClass("tool-settings-row__switch-track")
    expect(searchSwitch.lastElementChild).toHaveClass("tool-settings-row__switch-track")
    expect(screen.getByRole("switch", { name: "启用本地文件（只读）" })).toHaveAttribute("aria-checked", "false")
  })

  it("expands multiple rows inline without opening a dialog", async () => {
    // Given: the settings list has loaded.
    const user = userEvent.setup()
    renderPanel()
    const search = await screen.findByRole("button", { name: "展开网络搜索详情" })
    const localFileButton = screen.getByRole("button", { name: "展开本地文件（只读）详情" })

    // When: both rows are expanded.
    await user.click(search)
    await user.click(localFileButton)

    // Then: each row owns an accessible inline region and no dialog is created.
    expect(search).toHaveAttribute("aria-expanded", "true")
    expect(localFileButton).toHaveAttribute("aria-expanded", "true")
    expect(screen.getAllByText("收起配置")).toHaveLength(2)
    expect(document.querySelectorAll(".tool-settings-row__disclosure .lucide-chevron-up")).toHaveLength(2)
    expect(screen.getAllByRole("heading", { level: 3, name: "详细配置" })).toHaveLength(2)
    expect(screen.getByRole("region", { name: "网络搜索" })).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "本地文件（只读）" })).toBeInTheDocument()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("changes only the selected tool switch draft", async () => {
    // Given: the settings list has loaded.
    const user = userEvent.setup()
    renderPanel()
    await screen.findByRole("button", { name: "展开网络搜索详情" })
    const localSwitch = screen.getByRole("switch", { name: "启用本地文件（只读）" })

    // When: local file is enabled.
    await user.click(localSwitch)

    // Then: its draft changes without expanding a row or verifying a tool.
    expect(localSwitch).toHaveAttribute("aria-checked", "true")
    expect(screen.getByRole("button", { name: "展开网络搜索详情" })).toHaveAttribute("aria-expanded", "false")
    expect(api.verifyOwnerTool).not.toHaveBeenCalled()
  })

  it("shows tool-specific configuration, write-only secrets, and non-interactive future rows", async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.click(await screen.findByRole("button", { name: "展开网络搜索详情" }))

    expect(screen.getByRole("combobox", { name: "搜索 Provider" })).toBeInTheDocument()
    expect(document.getElementById("web-search-api-key")).toHaveValue("")
    expect(screen.queryByText("管理精灵可使用的本机工具。工具开关与调用策略分开生效，只有两者都满足时才会进入实际可用集合。")).not.toBeInTheDocument()
    expect(screen.queryByText("通过已配置的搜索 Provider 获取网页信息。")).not.toBeInTheDocument()
    expect(screen.queryByText("隔离与审批契约完成前不会开放。")).not.toBeInTheDocument()
    expect(screen.queryByText("已在本机配置；留空表示保留现有密钥。")).not.toBeInTheDocument()
    expect(screen.getByRole("heading", { level: 3, name: "调用策略" })).toBeInTheDocument()
    expect(screen.getByText("Python 代码执行")).toBeInTheDocument()
    expect(screen.queryByRole("switch", { name: /Python/ })).not.toBeInTheDocument()
  })

  it("submits the selected tool configuration separately from its permission policy", async () => {
    const user = userEvent.setup()
    api.updateOwnerTool.mockResolvedValue(localFile)
    renderPanel()
    await user.click(await screen.findByRole("button", { name: "展开本地文件（只读）详情" }))

    const readLimit = screen.getByDisplayValue("65536")
    await user.clear(readLimit)
    await user.type(readLimit, "131072")
    await user.tab()
    await user.click(screen.getByRole("button", { name: "保存工具设置" }))

    expect(api.updateOwnerTool).toHaveBeenCalledWith("local_file", { enabled: false, max_read_bytes: 131072 }, "csrf-token")
    expect(api.updateToolPermission).not.toHaveBeenCalled()
  })

  it("saves a permission policy without changing the tool configuration", async () => {
    const user = userEvent.setup()
    renderPanel()
    await user.click(await screen.findByRole("button", { name: "展开网络搜索详情" }))
    await user.click(screen.getByRole("combobox", { name: "调用策略" }))
    await user.click(screen.getByRole("option", { name: "拒绝" }))
    await user.click(screen.getByRole("button", { name: "保存调用策略" }))

    expect(api.updateToolPermission).toHaveBeenCalledWith("WEB_SEARCH", "deny", "csrf-token")
    expect(api.updateOwnerTool).not.toHaveBeenCalled()
  })

  it("keeps unsupported permission modes read-only", async () => {
    const user = userEvent.setup()
    api.ownerRuntimePolicy.mockResolvedValue({
      tool_permissions: {
        WEB_SEARCH: { mode: "ask", reason: "需要人工审批" },
        READ: policy.tool_permissions.READ,
      },
    })
    renderPanel()
    await user.click(await screen.findByRole("button", { name: "展开网络搜索详情" }))

    expect(screen.getByRole("combobox", { name: "调用策略" })).toBeDisabled()
  })
})
