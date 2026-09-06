import { render, screen, waitFor, within, type RenderResult } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { createI18n } from "../i18n/config"
import { ChatPage } from "./ChatPage"

const session = vi.hoisted(() => ({
  refresh: vi.fn(async () => undefined),
  refreshCsrfToken: vi.fn(async () => "csrf"),
  user: {
    avatar_color: 2,
    avatar_kind: "initials" as const,
    csrf_token: "csrf",
    default_landing_page: "chat" as const,
    account_id: "owner",
    display_name: "Owner",
    role: "owner" as const,
    theme_key: "warm-paper" as const,
    user_id: 1,
  },
}))

const chatApi = vi.hoisted(() => ({
  adoptionInfo: vi.fn(),
  conversations: vi.fn(),
  elfieFoodPolicy: vi.fn(),
  elfies: vi.fn(),
  messages: vi.fn(),
  profile: vi.fn(),
  discordAccount: vi.fn(),
  telegramAccount: vi.fn(),
  sendMessage: vi.fn(),
}))

vi.mock("../stores/session", () => ({
  useSession: () => ({ user: session.user, loading: false, refresh: session.refresh, refreshCsrfToken: session.refreshCsrfToken }),
}))

vi.mock("../stores/heartbeat", () => ({
  usePresenceHeartbeat: () => undefined,
}))

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return {
    ...original,
    adoptionInfo: chatApi.adoptionInfo,
    elfieFoodPolicy: chatApi.elfieFoodPolicy,
    elfies: chatApi.elfies,
    profile: chatApi.profile,
    discordAccount: chatApi.discordAccount,
    telegramAccount: chatApi.telegramAccount,
  }
})

vi.mock("../api/communication", () => ({
  conversations: chatApi.conversations,
  messages: chatApi.messages,
  sendMessage: chatApi.sendMessage,
}))

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
  appearance: null,
  big_five: {},
  personality_tags: [],
  status: { code: "at_nest", label: "在巢中", tone: "active" as const },
  nest: { room_name: null, bed_name: null, posture: "standing" },
  embodiment: { state: "at_nest" },
}

function profileDetail(source: typeof elfie) {
  return {
    relationship: "owned" as const,
    ...source,
    private_cognition: {
      status: "ready" as const,
      recent_focus: { topics: [{ id: "topic:门口", label: "门口", category: "place", weight: 1 }] },
      important_experiences: { entries: [] },
      relationship_world: {
        nodes: [{ id: "self", label: source.name, kind: "self" as const, weight: 1 }],
        edges: [],
      },
      world_understanding: {
        summary: "安静的地方让我放松。",
        rings: [
          { key: "self" as const, nodes: [] },
          { key: "family" as const, nodes: [] },
          { key: "nest" as const, nodes: [] },
          { key: "society" as const, nodes: [] },
          { key: "outside" as const, nodes: [] },
        ],
      },
      knowledge_beliefs: { nodes: [], edges: [] },
    },
    care_settings: {
      food: { selected_id: "", selected_label: "", options: [], unavailable: false },
    },
  }
}

describe("ChatPage profile integration", () => {
  beforeEach(() => {
    chatApi.adoptionInfo.mockResolvedValue({ species: [], quota: { used: 0, max: 3, remaining: 3, can_adopt: true }, nest_capacity: { used: 0, max: 3, remaining: 3 }, availability: "available", personality_styles: [], heights: [], builds: [], life_stages: [] })
    session.user.account_id = "admin123"
    session.user.role = "owner"
    window.history.replaceState({}, "", "/chat?view=conversation&elfie=00000001")
    chatApi.conversations.mockResolvedValue([{
      elfie_id: "00000001",
      name: "小羽",
      portrait_url: "",
      last_message_preview: "早上好",
      last_message_at: "2026-08-04T23:00:00Z",
    }])
    chatApi.elfies.mockResolvedValue([elfie])
    chatApi.elfieFoodPolicy.mockResolvedValue({
      effective_main_food_id: "",
      main_food_id: "",
      main_food_options: [],
      main_food_unavailable: false,
    })
    chatApi.messages.mockResolvedValue([])
    chatApi.profile.mockResolvedValue(profileDetail(elfie))
    chatApi.telegramAccount.mockResolvedValue({
      elfie_id: "00000001",
      state: "unconfigured",
      bot_username: null,
      bot_display_name: null,
      bound_telegram_username: null,
      bound_display_name: null,
      last_checked_at: null,
      issue: null,
    })
    chatApi.discordAccount.mockResolvedValue({
      elfie_id: "00000001",
      state: "unconfigured",
      bot_username: null,
      bot_display_name: null,
      bound_discord_username: null,
      bound_display_name: null,
      last_checked_at: null,
      issue: null,
    })
  })

  it("restores a profile deep link from the URL across a fresh render", async () => {
    window.history.replaceState({}, "", "/chat?view=profile&elfie=00000001")
    const firstRender = renderChatPage()
    expect(await screen.findByRole("heading", { level: 1, name: "小羽" })).toBeInTheDocument()
    expect(chatApi.profile).toHaveBeenCalledWith("00000001")
    expect(window.location.search).toBe("?view=profile&elfie=00000001")
    firstRender.unmount()
    renderChatPage()
    expect(await screen.findByRole("heading", { level: 1, name: "小羽" })).toBeInTheDocument()
    expect(window.location.search).toBe("?view=profile&elfie=00000001")
  })

  it("does not show a chat-load error while viewing another Elfie's profile", async () => {
    chatApi.messages.mockRejectedValue(new Error("history unavailable"))
    window.history.replaceState({}, "", "/chat?view=profile&elfie=00000001")

    renderChatPage()

    expect(await screen.findByRole("heading", { level: 1, name: "小羽" })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText("精灵不存在")).not.toBeInTheDocument())
  })

  it("threads the real API adopter identity into the profile projection", async () => {
    const realElfie = { ...elfie, elfie_id: "34567890", name: "Mochi" }
    window.history.replaceState({}, "", "/chat?view=profile&elfie=34567890")
    chatApi.conversations.mockResolvedValue([])
    chatApi.elfies.mockResolvedValue([realElfie])
    chatApi.profile.mockResolvedValue(profileDetail(realElfie))
    renderChatPage()
    expect(await screen.findByRole("heading", { level: 1, name: "Mochi" })).toBeInTheDocument()
    expect(screen.getByText("我")).toBeInTheDocument()
    expect(screen.getByText("领养日期")).toBeInTheDocument()
    expect(screen.getByText("年龄")).toBeInTheDocument()
  })

  it("routes profile and conversation actions through canonical history state", async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, "", "/chat?view=profile&elfie=00000001")
    renderChatPage()
    const rail = screen.getByLabelText("ElfieNest 导航")
    await user.click(await within(rail).findByRole("button", { name: "聊天记录" }))
    await waitFor(() => {
      expect(window.location.search).toBe("?view=conversation&elfie=00000001")
    })
    await user.click(screen.getByRole("button", { name: "详情" }))
    await waitFor(() => {
      expect(window.location.search).toBe("?view=profile&elfie=00000001")
    })
    await user.click(screen.getByRole("button", { name: "进入聊天" }))
    await waitFor(() => {
      expect(window.location.search).toBe("?view=conversation&elfie=00000001")
    })
    await user.click(screen.getByRole("button", { name: "详情" }))
    await waitFor(() => {
      expect(window.location.search).toBe("?view=profile&elfie=00000001")
    })
    await user.click(await screen.findByRole("button", { name: "返回我的精灵" }))
    await waitFor(() => {
      expect(window.location.search).toBe("?view=elfies")
    })
  })

  it("canonicalizes a nonexistent Elfie route to the stable list", async () => {
    window.history.replaceState({}, "", "/chat?view=profile&elfie=99999999")
    renderChatPage()
    await screen.findByRole("heading", { level: 1, name: "精灵" })
    await waitFor(() => {
      expect(window.location.search).toBe("?view=elfies")
    })
    await waitFor(() => {
      expect(screen.queryByRole("heading", { level: 1, name: "小羽" })).not.toBeInTheDocument()
    })
  })

  it("replaces a bad route so browser Back reaches the prior valid profile", async () => {
    window.history.replaceState({}, "", "/chat?view=profile&elfie=00000001")
    window.history.pushState({}, "", "/chat?view=profile&elfie=99999999")
    renderChatPage()
    await waitFor(() => {
      expect(window.location.search).toBe("?view=elfies")
    })
    const popped = new Promise<void>((resolve) => {
      window.addEventListener("popstate", () => resolve(), { once: true })
    })
    window.history.back()
    await popped
    expect(window.location.search).toBe("?view=profile&elfie=00000001")
    expect(await screen.findByRole("heading", { level: 1, name: "小羽" })).toBeInTheDocument()
  })
})

function renderChatPage(): RenderResult {
  const instance = createI18n()
  return render(
    <I18nextProvider i18n={instance}>
      <ChatPage />
    </I18nextProvider>,
  )
}
