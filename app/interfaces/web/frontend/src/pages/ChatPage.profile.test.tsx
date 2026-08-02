import { act, render, screen, waitFor, within, type RenderResult } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { PRIVATE_MODULE_TITLES } from "../components/elfie-profile/mock-data"
import { createI18n } from "../i18n/config"
import { navigate } from "../stores/history"
import { ChatPage } from "./ChatPage"

const session = vi.hoisted(() => ({
  refresh: vi.fn(async () => undefined),
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
}

describe("ChatPage profile integration", () => {
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

  it("restores a profile deep link from the URL across a fresh render", async () => {
    window.history.replaceState({}, "", "/chat?view=profile&elfie=00000001&mock=1")
    const firstRender = renderChatPage()
    expect(await screen.findByRole("heading", { level: 1, name: "小羽" })).toBeInTheDocument()
    expect(chatApi.profile).toHaveBeenCalledWith("00000001")
    expect(window.location.search).toBe("?view=profile&elfie=00000001&mock=1")
    firstRender.unmount()
    renderChatPage()
    expect(await screen.findByRole("heading", { level: 1, name: "小羽" })).toBeInTheDocument()
    expect(window.location.search).toBe("?view=profile&elfie=00000001&mock=1")
  })

  it("integrates the complete owner Happy profile without disturbing canonical chat routing", async () => {
    useDemoElfies()
    window.history.replaceState({}, "", "/chat?view=profile&elfie=12345678&mock=1")
    const { container } = renderChatPage()
    expect(await screen.findByRole("heading", { level: 1, name: "Happy" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { level: 2, name: "3D 个体视图" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { level: 2, name: "大五人格" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "拍照" })).toBeInTheDocument()
    for (const title of PRIVATE_MODULE_TITLES) {
      expect(screen.getByRole("button", { name: title })).toBeInTheDocument()
    }
    expect(container).not.toHaveTextContent(/精灵身份证|Observer|本地 3D 观察|修改/)
    await userEvent.click(screen.getByRole("button", { name: "进入聊天" }))
    await waitFor(() => {
      expect(window.location.search).toBe("?view=conversation&elfie=12345678&mock=1")
    })
    expect(screen.getByRole("button", { name: "详情" })).toBeInTheDocument()
  })

  it("integrates Kettle as a visitor with no capture or private cognition payload", async () => {
    useDemoElfies()
    window.history.replaceState({}, "", "/chat?view=elfies&mock=1")
    const { container } = renderChatPage()
    expect(await screen.findByText("Kettle", {}, { timeout: 5_000 })).toBeInTheDocument()

    act(() => navigate("/chat?view=profile&elfie=23456789&mock=1"))

    expect(await screen.findByRole("heading", { level: 1, name: "Kettle" }, { timeout: 5_000 })).toBeInTheDocument()
    expect(screen.getByRole("heading", { level: 2, name: "大五人格" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "拍照" })).not.toBeInTheDocument()
    for (const title of PRIVATE_MODULE_TITLES) {
      expect(screen.queryByRole("button", { name: title })).not.toBeInTheDocument()
    }
    expect(container).not.toHaveTextContent(/铜壶窗边观察|qwen3-8b-calm|第一次避让/)
  }, 10_000)

  it("threads the real API adopter identity into the profile projection", async () => {
    const realElfie = { ...elfie, elfie_id: "34567890", name: "Mochi" }
    window.history.replaceState({}, "", "/chat?view=profile&elfie=34567890&mock=1")
    chatApi.conversations.mockResolvedValue([])
    chatApi.elfies.mockResolvedValue([realElfie])
    chatApi.profile.mockResolvedValue(realElfie)
    renderChatPage()
    expect(await screen.findByRole("heading", { level: 1, name: "Mochi" })).toBeInTheDocument()
    expect(screen.getByText("我")).toBeInTheDocument()
    expect(screen.getByText("领养日期")).toBeInTheDocument()
    expect(screen.getByText("年龄")).toBeInTheDocument()
  })

  it("routes profile and conversation actions through canonical history state", async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, "", "/chat?view=profile&elfie=00000001&mock=1")
    renderChatPage()
    const rail = screen.getByLabelText("ElfieNest 导航")
    await user.click(await within(rail).findByRole("button", { name: "聊天记录" }))
    await waitFor(() => {
      expect(window.location.search).toBe("?view=conversation&elfie=00000001&mock=1")
    })
    await user.click(screen.getByRole("button", { name: "详情" }))
    await waitFor(() => {
      expect(window.location.search).toBe("?view=profile&elfie=00000001&mock=1")
    })
    await user.click(screen.getByRole("button", { name: "进入聊天" }))
    await waitFor(() => {
      expect(window.location.search).toBe("?view=conversation&elfie=00000001&mock=1")
    })
    await user.click(screen.getByRole("button", { name: "详情" }))
    await waitFor(() => {
      expect(window.location.search).toBe("?view=profile&elfie=00000001&mock=1")
    })
    await user.click(await screen.findByRole("button", { name: "返回我的精灵" }))
    await waitFor(() => {
      expect(window.location.search).toBe("?view=elfies&mock=1")
    })
  })

  it("canonicalizes a nonexistent Elfie route to the stable list without losing mock mode", async () => {
    window.history.replaceState({}, "", "/chat?view=profile&elfie=99999999&mock=1")
    renderChatPage()
    await screen.findByRole("heading", { level: 1, name: "精灵" })
    await waitFor(() => {
      expect(window.location.search).toBe("?view=elfies&mock=1")
    })
    expect(screen.queryByRole("heading", { level: 1, name: "小羽" })).not.toBeInTheDocument()
  })

  it("replaces a bad route so browser Back reaches the prior valid profile", async () => {
    window.history.replaceState({}, "", "/chat?view=profile&elfie=00000001&mock=1")
    window.history.pushState({}, "", "/chat?view=profile&elfie=99999999&mock=1")
    renderChatPage()
    await waitFor(() => {
      expect(window.location.search).toBe("?view=elfies&mock=1")
    })
    const popped = new Promise<void>((resolve) => {
      window.addEventListener("popstate", () => resolve(), { once: true })
    })
    window.history.back()
    await popped
    expect(window.location.search).toBe("?view=profile&elfie=00000001&mock=1")
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
