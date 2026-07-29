import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ChatPage } from "./ChatPage"

const chatStyles = readFileSync(resolve(import.meta.dirname, "../shared/chat-profile.css"), "utf8")

const session = vi.hoisted(() => ({
  refresh: vi.fn(async () => undefined),
  user: {
    avatar_color: 2,
    avatar_kind: "initials" as const,
    csrf_token: "csrf",
    default_landing_page: "chat" as const,
    account_id: "owner",
    nickname: "Owner",
    role: "owner" as const,
    theme_key: "warm-paper" as const,
    username: "owner",
  },
}))

const chatApi = vi.hoisted(() => ({
  conversations: vi.fn(),
  elfies: vi.fn(),
  messages: vi.fn(),
  profile: vi.fn(),
  sendMessage: vi.fn(),
}))

vi.mock("../stores/session", () => ({
  useSession: () => ({ user: session.user, loading: false, refresh: session.refresh }),
}))

vi.mock("../stores/heartbeat", () => ({
  usePresenceHeartbeat: () => undefined,
}))

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return { ...original, ...chatApi }
})

vi.mock("../api/chat-socket", () => ({
  ChatSocket: class {
    public connect(): void {}
    public send(): boolean { return false }
    public close(): void {}
  },
}))

vi.mock("../components/elfie-profile/ProfileChart", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../components/elfie-profile/ProfileChart")>()
  return {
    ...original,
    loadProfileChartRuntime: () => Promise.resolve({
      init: vi.fn(() => ({ dispose: vi.fn(), resize: vi.fn(), setOption: vi.fn() })),
    }),
  }
})

const elfie = {
  elfie_id: "00000001",
  name: "小羽",
  species_id: "星光精灵",
  gender: null,
  birth_date: null,
  summary: null,
  online_status: "online" as const,
  portrait_url: "",
  appearance: {},
  big_five: {},
  personality_tags: [],
  status: { code: "at_nest", label: "在巢中", tone: "active" as const },
  nest: { room_name: null, bed_name: null, posture: "standing" },
  embodiment: { state: "at_nest" },
}

function useDemoElfies(): void {
  chatApi.conversations.mockRejectedValue(new Error("Not Found"))
  chatApi.elfies.mockRejectedValue(new Error("Not Found"))
  window.history.replaceState({}, "", "/chat?view=elfies&mock=1")
}

describe("ChatPage list pane headings", () => {
  beforeEach(() => {
    session.user.account_id = "admin123"
    session.user.role = "owner"
    window.history.replaceState({}, "", "/chat?view=conversation&elfie=00000001&mock=1")
    chatApi.conversations.mockResolvedValue([{
      elfie_id: "00000001",
      name: "小羽",
      portrait_url: "",
      last_message_preview: "早上好",
      last_message_at: null,
    }])
    chatApi.elfies.mockResolvedValue([elfie])
    chatApi.messages.mockResolvedValue([])
    chatApi.profile.mockResolvedValue(elfie)
  })

  it("shows only the large messages heading while preserving rail names and tooltips", async () => {
    render(<ChatPage />)

    const listPane = await screen.findByRole("heading", { level: 1, name: "消息" })
    expect(screen.queryByText("聊天记录", { selector: ".brand" })).not.toBeInTheDocument()

    const rail = screen.getByLabelText("ElfieNest 导航")
    const chatRail = within(rail).getByRole("button", { name: "聊天记录" })
    expect(chatRail).toHaveAttribute("data-tooltip", "聊天记录")
    expect(listPane).toBeInTheDocument()
  })

  it("switches to one visible Elfie heading without the repeated eyebrow", async () => {
    const user = userEvent.setup()
    render(<ChatPage />)

    const rail = screen.getByLabelText("ElfieNest 导航")
    await user.click(await within(rail).findByRole("button", { name: "我的精灵" }))

    expect(screen.getByRole("heading", { level: 1, name: "精灵" })).toBeInTheDocument()
    expect(screen.queryByText("我的精灵", { selector: ".brand" })).not.toBeInTheDocument()
    expect(screen.getByPlaceholderText("搜索精灵")).toBeInTheDocument()
  })

  it("uses a three-item mobile tab bar without manage or QR shortcuts", async () => {
    render(<ChatPage />)

    const mobileTabs = screen.getByLabelText("聊天移动导航")
    expect(mobileTabs.closest(".chat-page")).toBeInTheDocument()
    expect(await within(mobileTabs).findByRole("button", { name: "聊天记录" })).toHaveTextContent("消息")
    expect(within(mobileTabs).getByRole("button", { name: "我的精灵" })).toHaveTextContent("精灵")
    expect(within(mobileTabs).getByRole("button", { name: "我的" })).toHaveTextContent("我的")
    expect(within(mobileTabs).queryByRole("button", { name: "进入管理" })).not.toBeInTheDocument()
    expect(within(mobileTabs).queryByRole("button", { name: "扫码用手机打开聊天" })).not.toBeInTheDocument()
    expect(chatStyles).toContain(".app-rail { display: none; }")
    expect(chatStyles).toContain(".mobile-tabbar")
    const finalMobileRules = chatStyles.slice(chatStyles.indexOf("@media (max-width: 760px)"))
    const workbenchRule = finalMobileRules.match(/\.chat-workbench\s*\{[^}]+\}/)?.[0] ?? ""
    expect(workbenchRule).toContain("grid-template-columns: 1fr")
    expect(workbenchRule).toContain("grid-template-rows: minmax(0, 1fr)")
    expect(workbenchRule).toContain("overflow: hidden")
    expect(finalMobileRules).toContain("body:has(.chat-page)")
    expect(finalMobileRules).toContain("overscroll-behavior: none")
    expect(finalMobileRules).toContain("overscroll-behavior: contain")
    expect(chatStyles).toContain("gap: 0")
    expect(chatStyles).toContain(".mobile-tabbar__item > svg { width: 30px; height: 30px; }")
    expect(chatStyles).toContain("width: 32px")
    expect(chatStyles).toContain("height: 32px")
    expect(workbenchRule).not.toContain("padding-bottom")
    expect(finalMobileRules).toContain(".app-rail { display: none; }")
    expect(finalMobileRules).toContain(".connection-state { display: none; }")
  })

  it("keeps the chat layout reviewable with demo data when the legacy chat API is unavailable", async () => {
    chatApi.conversations.mockRejectedValue(new Error("Not Found"))
    chatApi.elfies.mockRejectedValue(new Error("Not Found"))
    window.history.replaceState({}, "", "/chat?view=conversation&elfie=12345678&mock=1")

    render(<ChatPage />)

    expect((await screen.findAllByText("Happy")).length).toBeGreaterThan(0)
    expect(screen.getByText("后端暂不可用，当前显示演示数据")).toBeInTheDocument()
  })

  it("searches Elfies and shows account-owned filter counts in deterministic groups", async () => {
    const user = userEvent.setup()
    useDemoElfies()
    render(<ChatPage />)

    const allFilter = await screen.findByRole("button", { name: "全部 2" })
    expect(screen.getByRole("button", { name: "我的 1" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "其他 1" })).toBeInTheDocument()
    expect(allFilter).toHaveAttribute("aria-pressed", "true")
    const groupHeadings = screen.getAllByRole("heading", { level: 2 })
    expect(groupHeadings.map((heading) => heading.textContent)).toEqual(["我的精灵", "其他精灵"])

    await user.click(screen.getByRole("button", { name: "我的 1" }))
    expect(screen.getByText("Happy")).toBeInTheDocument()
    expect(screen.queryByText("Kettle")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "其他 1" }))
    expect(screen.queryByText("Happy")).not.toBeInTheDocument()
    expect(screen.getByText("Kettle")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "全部 2" }))

    const search = screen.getByPlaceholderText("搜索精灵")
    await user.type(search, "KETTLE")
    expect(screen.queryByText("Happy")).not.toBeInTheDocument()
    expect(screen.getByText("Kettle")).toBeInTheDocument()

    await user.clear(search)
    await user.type(search, "12345678")
    expect(screen.getByText("Happy")).toBeInTheDocument()
    expect(screen.queryByText("Kettle")).not.toBeInTheDocument()

    await user.clear(search)
    await user.type(search, "FOX")
    expect(screen.getByText("Happy")).toBeInTheDocument()
    expect(screen.getByText("Kettle")).toBeInTheDocument()
  })

  it("does not infer adoption ownership from the platform owner role", async () => {
    const user = userEvent.setup()
    useDemoElfies()
    session.user.account_id = "unrelated-owner"
    session.user.role = "owner"
    render(<ChatPage />)

    expect(await screen.findByRole("button", { name: "我的 0" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "其他 2" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "我的 0" }))
    expect(screen.getByRole("status")).toHaveTextContent("没有符合条件的精灵")
  })

  it("keeps row profile and chat navigation distinct without nested controls", async () => {
    const user = userEvent.setup()
    useDemoElfies()
    render(<ChatPage />)

    const chat = await screen.findByRole("button", { name: "与 Kettle 聊天" })
    const listRow = chat.closest("article")
    if (!(listRow instanceof HTMLElement)) throw new TypeError("Expected an Elfie list row")
    expect(within(listRow).getAllByRole("button")).toHaveLength(2)
    expect(chat.closest(".elfie-list__profile")).toBeNull()
    await user.click(chat)
    await waitFor(() => {
      expect(window.location.search).toBe("?view=conversation&elfie=23456789&mock=1")
    })

    window.history.replaceState({}, "", "/chat?view=elfies&mock=1")
    window.dispatchEvent(new PopStateEvent("popstate"))
    const profileRow = await screen.findByRole("button", { name: "查看 Happy 的个人档案" })
    await user.click(profileRow)
    await waitFor(() => {
      expect(window.location.search).toBe("?view=profile&elfie=12345678&mock=1")
    })
  })

  it("announces no results and recovers when the controlled search is cleared", async () => {
    const user = userEvent.setup()
    useDemoElfies()
    render(<ChatPage />)

    const search = await screen.findByPlaceholderText("搜索精灵")
    await user.type(search, "999999999999999999")
    expect(screen.getByRole("status")).toHaveTextContent("没有符合条件的精灵")
    expect(window.location.search).toBe("?view=elfies&mock=1")

    await user.clear(search)
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
    expect(screen.getByText("Happy")).toBeInTheDocument()
  })
})
