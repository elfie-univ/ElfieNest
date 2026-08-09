import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ownerElfies, ownerRead, ownerRooms, ownerWrite } from "../api/client"
import { ApiError } from "../api/http"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
import { SystemSettingsPanel } from "./SystemSettingsPanel"
import { useToolsPermissions } from "./tools/useToolsPermissions"
import { ToastProvider } from "./ui/toast"

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return {
    ...original,
    ownerElfies: vi.fn(),
    ownerRead: vi.fn(),
    ownerRooms: vi.fn(),
    ownerWrite: vi.fn(),
  }
})

vi.mock("./tools/useToolsPermissions", () => ({ useToolsPermissions: vi.fn() }))

const engine = { tick_interval_sec: 1.5 }
const adoption = { max_elfies_per_user: 3, allowed_species_ids: ["dog", "fox"], personality_presets_enabled: {} }
const security = { session_ttl_days: 7, rate_limit: { max_attempts: 5, window_seconds: 60 } }
const tools = {
  web_search: {
    enabled: true,
    provider: "duckduckgo",
    api_base: "https://duckduckgo.com",
    max_results: 3,
    max_result_bytes: 16_000,
    timeout_seconds: 5,
    max_tool_calls: 3,
    max_total_result_bytes: 48_000,
    has_api_key: false,
  },
  local_file: {
    enabled: false,
    root: "",
    root_policy: "elfie_workspace",
    max_read_bytes: 65_536,
    max_items: 200,
    max_result_bytes: 16_000,
    max_tool_calls: 3,
    max_total_result_bytes: 48_000,
    has_api_key: false,
  },
} as const

describe("SystemSettingsPanel", () => {
  beforeEach(() => {
    vi.mocked(ownerRead).mockImplementation(async (path) => {
      if (path.endsWith("/engine")) return engine
      if (path.endsWith("/adoption")) return adoption
      if (path.endsWith("/security")) return security
      throw new Error(`Unexpected owner read: ${path}`)
    })
    vi.mocked(ownerRooms).mockResolvedValue([{ id: "local-nest", name: "精灵巢", desired_bed_count: 4, beds: [] }])
    vi.mocked(ownerElfies).mockResolvedValue([{} as never, {} as never])
    vi.mocked(ownerWrite).mockResolvedValue({})
    vi.mocked(useToolsPermissions).mockReturnValue({
      cancelTool: vi.fn(),
      changeLocalFile: vi.fn(),
      changeWebSearch: vi.fn(),
      dirtyTools: [],
      drafts: { web_search: { ...tools.web_search, api_key: "" }, local_file: tools.local_file },
      error: null,
      saveTool: vi.fn(async () => undefined),
      savingTool: null,
      toolErrors: { web_search: null, local_file: null },
      toggleTool: vi.fn(),
      verification: { web_search: null, local_file: null },
      verifyTool: vi.fn(async () => undefined),
      verifying: null,
    })
  })

  it("consolidates quota, capability configuration, and collapsed advanced settings", async () => {
    const user = userEvent.setup()
    renderSettingsPanel()

    expect(document.querySelector(".system-settings")).toHaveClass("manage-card", "manage-card--wide")
    expect(await screen.findByRole("heading", { name: "精灵额度" })).toBeInTheDocument()
    expect(screen.getByText("4 只")).toBeInTheDocument()
    expect(screen.getAllByText("2 只", { selector: "strong" })).toHaveLength(2)
    const nestLink = screen.getByRole("link", { name: "配置前往…" })
    expect(nestLink).toHaveAttribute("href", "/manage?section=nest")
    expect(nestLink).toHaveAttribute("title", "配置请前往精灵巢管理")
    expect(screen.getByText("当前精灵巢容量").closest(".system-quota__stat")).toContainElement(nestLink)
    expect(screen.getByRole("button", { name: "重新读取" }).closest(".manage-head")).toContainElement(screen.getByRole("button", { name: "重新读取" }))
    expect(screen.queryByText("影响整套 ElfieNest 与唯一精灵巢的全局配置。")).not.toBeInTheDocument()
    expect(screen.queryByText("全局容量与成员默认额度")).not.toBeInTheDocument()
    expect(screen.queryByText("总容量由唯一精灵巢的床位数决定，这里只读。")).not.toBeInTheDocument()
    expect(screen.queryByText("新成员和未单独设置额度的成员使用此默认值。")).not.toBeInTheDocument()

    expect(screen.getByRole("heading", { name: "系统能力" })).toBeInTheDocument()
    expect(screen.getByText("网络搜索")).toBeInTheDocument()
    expect(screen.getByText("本地文件（只读）")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "展开网络搜索详情" })).toBeInTheDocument()
    expect(document.getElementById("tool-web_search-details")).toHaveAttribute("hidden")
    expect(screen.queryByText("调用策略")).not.toBeInTheDocument()
    expect(screen.queryByText("暂未开放的能力")).not.toBeInTheDocument()
    expect(screen.queryByText("最近运行观测")).not.toBeInTheDocument()
    expect(screen.queryByText("每项能力都有独立配置与验证")).not.toBeInTheDocument()
    expect(screen.queryByText("timeout")).not.toBeInTheDocument()
    expect(screen.queryByText("max_tool_calls")).not.toBeInTheDocument()
    expect(screen.queryByText("max_total_result_bytes")).not.toBeInTheDocument()
    expect(screen.queryByText("root_policy")).not.toBeInTheDocument()
    expect(screen.queryByText("max_items")).not.toBeInTheDocument()
    expect(screen.queryByText("max_result_bytes")).not.toBeInTheDocument()

    expect(screen.queryByText("会话有效期（天）")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "展开高级设置" }))
    expect(screen.getByText("会话有效期（天）")).toBeInTheDocument()
    expect(screen.getByText("运行 Tick（秒）")).toBeInTheDocument()
    expect(screen.queryByText("影响之后新签发的登录会话。")).not.toBeInTheDocument()
    expect(screen.queryByText("限制每房精灵数")).not.toBeInTheDocument()
    expect(screen.queryByText("允许物种")).not.toBeInTheDocument()
  })

  it("saves the default member quota without changing hidden adoption settings", async () => {
    const user = userEvent.setup()
    renderSettingsPanel()

    await user.click(await screen.findByRole("button", { name: "增加每位成员默认最多领养" }))
    await user.click(screen.getByRole("button", { name: "保存默认额度" }))

    await waitFor(() => expect(vi.mocked(ownerWrite)).toHaveBeenCalledWith(
      "/api/owner/system/adoption",
      "PUT",
      "csrf",
      { ...adoption, max_elfies_per_user: 4 },
    ))
  })

  it("keeps localized save failures inside the system settings page", async () => {
    const user = userEvent.setup()
    vi.mocked(ownerWrite).mockRejectedValueOnce(new ApiError(400, "后端拒绝了系统设置"))
    renderSettingsPanel("en-US")

    await screen.findByRole("heading", { name: "Elfie quota" })
    await user.click(screen.getByRole("button", { name: "Save default quota" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to save management data.")
    expect(screen.queryByText("后端拒绝了系统设置")).not.toBeInTheDocument()
  })
})

function renderSettingsPanel(locale: SupportedLocale = "zh-CN"): void {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  document.documentElement.lang = locale
  render(
    <I18nextProvider i18n={instance}>
      <ToastProvider><SystemSettingsPanel csrfToken="csrf" /></ToastProvider>
    </I18nextProvider>,
  )
}
