import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ChatPage } from "./ChatPage"

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

    await user.click(await screen.findByRole("button", { name: "我的精灵" }))

    expect(screen.getByRole("heading", { level: 1, name: "精灵" })).toBeInTheDocument()
    expect(screen.queryByText("我的精灵", { selector: ".brand" })).not.toBeInTheDocument()
    expect(screen.getByPlaceholderText("搜索精灵")).toBeInTheDocument()
  })

  it("keeps the chat layout reviewable with demo data when the legacy chat API is unavailable", async () => {
    chatApi.conversations.mockRejectedValue(new Error("Not Found"))
    chatApi.elfies.mockRejectedValue(new Error("Not Found"))

    render(<ChatPage />)

    expect((await screen.findAllByText("Happy")).length).toBeGreaterThan(0)
    expect(screen.getByText("后端暂不可用，当前显示演示数据")).toBeInTheDocument()
  })
})
