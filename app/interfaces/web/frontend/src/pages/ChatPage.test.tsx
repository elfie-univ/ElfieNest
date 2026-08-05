import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { act, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { i18n } from "i18next"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { ChatSocketEvent, ChatSocketStatus } from "../api/chat-socket"
import { ApiError } from "../api/http"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
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
    display_name: "Owner",
    avatar_url: null as string | null,
    role: "owner" as const,
    theme_key: "warm-paper" as const,
    user_id: 1,
  },
}))

const chatApi = vi.hoisted(() => ({
  conversations: vi.fn(),
  elfies: vi.fn(),
  messages: vi.fn(),
  profile: vi.fn(),
  sendMessage: vi.fn(),
}))

type SocketCallbacks = {
  readonly onEvent: (event: ChatSocketEvent) => void
  readonly onStatus: (status: ChatSocketStatus) => void
}

const socketState = vi.hoisted<{ callbacks: SocketCallbacks | null }>(() => ({
  callbacks: null,
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
    public constructor(callbacks: SocketCallbacks) { socketState.callbacks = callbacks }
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

describe("ChatPage list pane headings", () => {
  beforeEach(() => {
    session.user.account_id = "admin123"
    session.user.role = "owner"
    session.user.avatar_url = null
    window.history.replaceState({}, "", "/chat?view=conversation&elfie=00000001")
    chatApi.conversations.mockResolvedValue([{
      elfie_id: "00000001",
      name: "小羽",
      portrait_url: "",
      last_message_preview: "早上好",
      last_message_at: "2026-08-04T23:00:00Z",
    }])
    chatApi.elfies.mockResolvedValue([elfie])
    chatApi.messages.mockResolvedValue([])
    chatApi.profile.mockResolvedValue(elfie)
    chatApi.sendMessage.mockResolvedValue({
      id: 1,
      elfie_id: "00000001",
      sender: "user",
      text: "hello",
      created_at: "2026-07-29T00:00:00Z",
    })
    socketState.callbacks = null
  })

  it("shows only the large messages heading while preserving rail names and tooltips", async () => {
    renderChatPage("zh-CN")

    const listPane = await screen.findByRole("heading", { level: 1, name: "消息" })
    expect(screen.queryByText("聊天记录", { selector: ".brand" })).not.toBeInTheDocument()

    const rail = screen.getByLabelText("ElfieNest 导航")
    const chatRail = within(rail).getByRole("button", { name: "聊天记录" })
    expect(chatRail).toHaveAttribute("data-tooltip", "聊天记录")
    expect(listPane).toBeInTheDocument()
  })

  it("opens chat history by default even when there are no Elfies", async () => {
    window.history.replaceState({}, "", "/chat")
    chatApi.conversations.mockResolvedValue([])
    chatApi.elfies.mockResolvedValue([])

    renderChatPage("zh-CN")

    expect(await screen.findByRole("heading", { level: 1, name: "消息" })).toBeInTheDocument()
    expect(await screen.findByText("还没有聊天记录。")).toBeInTheDocument()
    expect(screen.getByText("先在“我的精灵”中领养或选择一只精灵。")).toBeInTheDocument()
    await waitFor(() => expect(window.location.search).toBe("?view=chats"))
  })

  it("opens history when the chat rail is selected from the Elfie list without a selection", async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, "", "/chat?view=elfies")
    chatApi.conversations.mockResolvedValue([])

    renderChatPage("zh-CN")
    const rail = await screen.findByLabelText("ElfieNest 导航")
    await user.click(within(rail).getByRole("button", { name: "聊天记录" }))

    await waitFor(() => expect(window.location.search).toBe("?view=chats"))
    expect(screen.getByRole("heading", { level: 1, name: "消息" })).toBeInTheDocument()
  })

  it("adds a history row only after a successful first message", async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, "", "/chat?view=conversation&elfie=00000001")
    chatApi.conversations.mockResolvedValue([])
    chatApi.messages.mockResolvedValue([])
    chatApi.sendMessage.mockResolvedValue({
      id: 10,
      elfie_id: "00000001",
      sender: "user",
      text: "第一次聊天",
      created_at: "2026-08-05T01:02:03Z",
    })

    renderChatPage("zh-CN")
    const composer = await screen.findByPlaceholderText("对 小羽 说点什么…")
    await user.type(composer, "第一次聊天")
    await user.click(screen.getByRole("button", { name: "发送" }))

    await waitFor(() => {
      const list = document.querySelector(".chat-list")
      if (!(list instanceof HTMLElement)) throw new TypeError("Expected chat list")
      expect(within(list).getByRole("button")).toHaveTextContent("小羽")
    })
  })

  it("does not create a history row for a failed first message and de-duplicates live events", async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, "", "/chat?view=conversation&elfie=00000001")
    chatApi.conversations.mockResolvedValue([])
    chatApi.messages.mockResolvedValue([])
    chatApi.sendMessage.mockRejectedValue(new ApiError(500, "send failed"))

    renderChatPage("zh-CN")
    const composer = await screen.findByPlaceholderText("对 小羽 说点什么…")
    await user.type(composer, "发送失败")
    await user.click(screen.getByRole("button", { name: "发送" }))

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("send failed"))
    const list = document.querySelector(".chat-list")
    if (!(list instanceof HTMLElement)) throw new TypeError("Expected chat list")
    expect(within(list).queryByRole("button")).not.toBeInTheDocument()

    const callbacks = socketState.callbacks
    if (callbacks === null) throw new TypeError("Expected socket callbacks")
    const message = {
      id: 11,
      elfie_id: "00000001" as const,
      sender: "elfie" as const,
      text: "收到消息",
      created_at: "2026-08-05T01:03:03Z",
    }
    act(() => callbacks.onEvent({ event: "message", message }))
    act(() => callbacks.onEvent({ event: "message", message }))

    await waitFor(() => expect(within(list).getAllByRole("button")).toHaveLength(1))
  })

  it("adds a live history row for another Elfie without changing the open conversation", async () => {
    const secondElfie = { ...elfie, elfie_id: "00000002", name: "阿栗" }
    window.history.replaceState({}, "", "/chat?view=conversation&elfie=00000001")
    chatApi.conversations.mockResolvedValue([])
    chatApi.elfies.mockResolvedValue([elfie, secondElfie])
    chatApi.messages.mockResolvedValue([])

    renderChatPage("zh-CN")
    await screen.findByPlaceholderText("对 小羽 说点什么…")
    const callbacks = socketState.callbacks
    if (callbacks === null) throw new TypeError("Expected socket callbacks")
    act(() => callbacks.onEvent({
      event: "message",
      message: {
        id: 12,
        elfie_id: "00000002",
        sender: "elfie",
        text: "另一只精灵的消息",
        created_at: "2026-08-05T01:04:03Z",
      },
    }))

    await waitFor(() => {
      const list = document.querySelector(".chat-list")
      if (!(list instanceof HTMLElement)) throw new TypeError("Expected chat list")
      expect(within(list).getByRole("button")).toHaveTextContent("阿栗")
    })
    expect(window.location.search).toBe("?view=conversation&elfie=00000001")
  })

  it("switches to one visible Elfie heading without the repeated eyebrow", async () => {
    const user = userEvent.setup()
    renderChatPage("zh-CN")

    const rail = screen.getByLabelText("ElfieNest 导航")
    await user.click(await within(rail).findByRole("button", { name: "精灵列表" }))

    expect(screen.getByRole("heading", { level: 1, name: "精灵" })).toBeInTheDocument()
    expect(screen.queryByText("我的精灵", { selector: ".brand" })).not.toBeInTheDocument()
    expect(screen.getByPlaceholderText("搜索精灵")).toBeInTheDocument()
  })

  it("uses a three-item mobile tab bar without manage or QR shortcuts", async () => {
    renderChatPage("zh-CN")

    const mobileTabs = screen.getByLabelText("聊天移动导航")
    expect(mobileTabs.closest(".chat-page")).toBeInTheDocument()
    expect(await within(mobileTabs).findByRole("button", { name: "聊天记录" })).toHaveTextContent("消息")
    expect(within(mobileTabs).getByRole("button", { name: "精灵列表" })).toHaveTextContent("精灵")
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
    const tabbarRule = finalMobileRules.match(/\.mobile-tabbar\s*\{[^}]+\}/)?.[0] ?? ""
    const tabItemRule = finalMobileRules.match(/\.mobile-tabbar__item\s*\{[^}]+\}/)?.[0] ?? ""
    expect(tabbarRule).toContain("grid-template-columns: repeat(3, minmax(0, 1fr));")
    expect(tabbarRule).toContain("padding: 6px 0 calc(6px + env(safe-area-inset-bottom));")
    expect(tabItemRule).toContain("width: 100%;")
    expect(tabItemRule).toContain("min-width: 0;")
    expect(chatStyles).toContain(".mobile-tabbar__item > svg { width: 30px; height: 30px; }")
    expect(chatStyles).toContain("width: 32px")
    expect(chatStyles).toContain("height: 32px")
    expect(workbenchRule).not.toContain("padding-bottom")
    expect(finalMobileRules).toContain(".app-rail { display: none; }")
    expect(chatStyles).not.toContain(".connection-state")
  })

  it("shows a real-data error instead of inventing demo records when the APIs fail", async () => {
    chatApi.conversations.mockRejectedValue(new Error("Not Found"))
    chatApi.elfies.mockRejectedValue(new Error("Not Found"))
    window.history.replaceState({}, "", "/chat?view=conversation&elfie=12345678")

    renderChatPage("zh-CN")

    expect(await screen.findByRole("alert")).toHaveTextContent("聊天内容加载失败")
    expect(screen.queryByText("Happy")).not.toBeInTheDocument()
    expect(screen.queryByText("Kettle")).not.toBeInTheDocument()
  })

  it("uses the authenticated account avatar for user messages", async () => {
    session.user.avatar_url = "/api/auth/me/avatar"
    chatApi.messages.mockResolvedValue([{
      id: 9,
      elfie_id: "00000001",
      sender: "user",
      text: "来自当前用户",
      created_at: "2026-07-29T00:00:00Z",
    }])

    renderChatPage("zh-CN")

    const message = await screen.findByText("来自当前用户")
    const article = message.closest("article")
    expect(article?.querySelector("img")).toHaveAttribute("src", "/api/auth/me/avatar")
  })

  it("sends a message with plain Enter while keeping Shift+Enter available for new lines", async () => {
    const user = userEvent.setup()
    renderChatPage("zh-CN")
    const composer = await screen.findByPlaceholderText("对 小羽 说点什么…")

    await user.type(composer, "回车发送")
    await user.keyboard("{Enter}")
    await waitFor(() => expect(chatApi.sendMessage).toHaveBeenCalledWith("00000001", "回车发送", "csrf"))

    await user.type(composer, "换行")
    await user.keyboard("{Shift>}{Enter}{/Shift}")
    expect(composer).toHaveValue("换行\n")
  })

  it("searches the real Elfie response and shows account-owned filter counts", async () => {
    const user = userEvent.setup()
    renderChatPage("zh-CN")

    const rail = screen.getByLabelText("ElfieNest 导航")
    await user.click(within(rail).getByRole("button", { name: "精灵列表" }))

    const allFilter = await screen.findByRole("button", { name: "全部 1" })
    expect(screen.getByRole("button", { name: "我的 1" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "其他 0" })).toBeInTheDocument()
    expect(allFilter).toHaveAttribute("aria-pressed", "true")
    const groupHeadings = screen.getAllByRole("heading", { level: 2 })
    expect(groupHeadings.map((heading) => heading.textContent)).toEqual(["我的精灵"])

    await user.click(screen.getByRole("button", { name: "我的 1" }))
    expect(screen.getByText("小羽")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "其他 0" }))
    expect(screen.getByRole("status")).toHaveTextContent("没有符合条件的精灵")
    await user.click(screen.getByRole("button", { name: "全部 1" }))

    const search = screen.getByPlaceholderText("搜索精灵")
    await user.type(search, "小羽")
    expect(screen.getByText("小羽")).toBeInTheDocument()

    await user.clear(search)
    await user.type(search, "00000001")
    expect(screen.getByText("小羽")).toBeInTheDocument()

    await user.clear(search)
    await user.type(search, "星光精灵")
    expect(screen.getByText("小羽")).toBeInTheDocument()
  })

  it("announces no results and recovers when the controlled search is cleared", async () => {
    const user = userEvent.setup()
    renderChatPage("zh-CN")
    const rail = screen.getByLabelText("ElfieNest 导航")
    await user.click(within(rail).getByRole("button", { name: "精灵列表" }))

    const search = await screen.findByPlaceholderText("搜索精灵")
    await user.type(search, "999999999999999999")
    expect(screen.getByRole("status")).toHaveTextContent("没有符合条件的精灵")
    expect(window.location.search).toBe("?view=elfies")

    await user.clear(search)
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
    expect(screen.getByText("小羽")).toBeInTheDocument()
  })

  it("hides REST load detail in English and preserves it in Chinese", async () => {
    // Given: history loading rejects with backend detail.
    chatApi.messages.mockRejectedValue(new ApiError(503, "后端失败"))

    // When: the real page loads in English.
    renderChatPage("en-US")

    // Then: only the closed chat-load fallback is visible.
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load chat content.")
    expect(screen.queryByText("后端失败")).not.toBeInTheDocument()
  })

  it("renders the Chat shell in English without translating conversation content", async () => {
    // Given: the Chat page has an active conversation with Chinese user content.
    chatApi.messages.mockResolvedValue([{
      id: 7,
      elfie_id: "00000001",
      sender: "elfie",
      text: "这是不会翻译的消息",
      created_at: "2026-07-29T00:00:00Z",
    }])

    // When: the page renders in English.
    renderChatPage("en-US")

    // Then: UI chrome is English while names, previews, and messages are byte-identical.
    expect(await screen.findByRole("heading", { level: 1, name: "Messages" })).toBeInTheDocument()
    expect(screen.getByLabelText("ElfieNest navigation")).toBeInTheDocument()
    expect(screen.getByPlaceholderText("Say something to 小羽...")).toBeInTheDocument()
    expect(screen.getByText("Send")).toBeInTheDocument()
    expect(screen.getByText("早上好")).toBeInTheDocument()
    expect(screen.getByText("这是不会翻译的消息")).toBeInTheDocument()
  })

  it("preserves live Chat state and closes existing backend detail when locale changes", async () => {
    // Given: an active Chinese conversation has a draft, search text, scroll, and live error state.
    const user = userEvent.setup()
    const instance = renderChatPage("zh-CN")
    const composer = await screen.findByPlaceholderText("对 小羽 说点什么…")
    const search = screen.getByPlaceholderText("搜索聊天")
    await user.type(composer, "逐字保留 draft 123")
    await user.type(search, "小羽 search 456")
    const messageList = document.querySelector(".message-list")
    if (!(messageList instanceof HTMLElement)) throw new TypeError("Expected message list")
    messageList.scrollTop = 137
    const callbacks = socketState.callbacks
    if (callbacks === null) throw new TypeError("Expected socket callbacks")
    act(() => {
      callbacks.onStatus("online")
      callbacks.onEvent({ event: "error", detail: "后端内部 detail" })
    })
    const locationBefore = `${window.location.pathname}${window.location.search}`
    expect(await screen.findByRole("alert")).toHaveTextContent("后端内部 detail")

    // When: the same mounted page changes locale.
    await act(async () => { await instance.changeLanguage("en-US") })

    // Then: chrome and privacy update, while product state remains byte-identical.
    expect(screen.getByRole("heading", { level: 1, name: "Messages" })).toBeInTheDocument()
    expect(screen.getByDisplayValue("逐字保留 draft 123")).toBe(composer)
    expect(screen.getByDisplayValue("小羽 search 456")).toBe(search)
    expect(messageList.scrollTop).toBe(137)
    expect(window.location.pathname + window.location.search).toBe(locationBefore)
    expect(screen.queryByText("Channel: Live")).not.toBeInTheDocument()
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to connect to chat.")
    expect(screen.queryByText("后端内部 detail")).not.toBeInTheDocument()
  })

  it("removes the connection status from both chat list panes", async () => {
    // Given: the English Chat shell is showing the conversation list.
    const user = userEvent.setup()
    renderChatPage("en-US")
    await screen.findByRole("heading", { level: 1, name: "Messages" })

    // When: the user switches to the Elfie list.
    expect(screen.queryByText("Channel: Live")).not.toBeInTheDocument()
    const rail = screen.getByLabelText("ElfieNest navigation")
    await user.click(within(rail).getByRole("button", { name: "Elfie list" }))

    // Then: neither list pane renders a connection status.
    await screen.findByRole("heading", { level: 1, name: "Elfies" })
    expect(screen.queryByText("Channel: Live")).not.toBeInTheDocument()
  })

  it.each(["后端失败", "upstream socket rejected credentials"])(
    "hides WebSocket detail in English: %s",
    async (detail) => {
      // Given: the real page is connected through the typed socket callback.
      renderChatPage("en-US")
      await screen.findByRole("heading", { name: "小羽" })
      const callbacks = socketState.callbacks
      if (callbacks === null) throw new TypeError("Expected socket callbacks")

      // When: a typed backend error event arrives.
      act(() => callbacks.onEvent({ event: "error", detail }))

      // Then: English shows only the closed connect fallback.
      expect(await screen.findByRole("alert")).toHaveTextContent("Unable to connect to chat.")
      expect(screen.queryByText(detail)).not.toBeInTheDocument()
    },
  )

  it("preserves WebSocket detail in Chinese", async () => {
    // Given: the real page is connected through the typed socket callback.
    renderChatPage("zh-CN")
    await screen.findByRole("heading", { name: "小羽" })
    const callbacks = socketState.callbacks
    if (callbacks === null) throw new TypeError("Expected socket callbacks")

    // When: a typed backend error event arrives.
    act(() => callbacks.onEvent({ event: "error", detail: "后端失败" }))

    // Then: Chinese preserves the useful detail.
    expect(await screen.findByRole("alert")).toHaveTextContent("后端失败")
  })

  it("hides REST send detail in English", async () => {
    // Given: the REST fallback sender rejects with backend detail.
    const user = userEvent.setup()
    chatApi.sendMessage.mockRejectedValue(new ApiError(500, "send failed upstream"))
    renderChatPage("en-US")

    // When: the user submits a message while the socket cannot send.
    const composer = await screen.findByPlaceholderText("Say something to 小羽...")
    await user.type(composer, "hello")
    await user.click(screen.getByRole("button", { name: "Send" }))

    // Then: only the closed send fallback is visible.
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to send the message.")
    expect(screen.queryByText("send failed upstream")).not.toBeInTheDocument()
  })
})

function renderChatPage(locale: SupportedLocale): i18n {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  document.documentElement.lang = locale
  render(
    <I18nextProvider i18n={instance}>
      <ChatPage />
    </I18nextProvider>,
  )
  return instance
}
