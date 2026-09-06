import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ownerRooms, type ClientUser } from "../api/client"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
import { useSession } from "../stores/session"
import { MonitorPage } from "./MonitorPage"

vi.mock("../stores/session", () => ({ useSession: vi.fn() }))

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return { ...original, ownerRooms: vi.fn() }
})

vi.mock("../components/ObservationMonitor", () => ({
  ObservationMonitor: ({ bedCount, roomId }: { readonly bedCount: number; readonly roomId: string }) => <section aria-label="房间 3D 观察" data-bed-count={String(bedCount)} data-room-id={roomId} data-slot="observation-monitor" role="region" />,
}))

const owner = {
  account_id: "owner",
  avatar_color: 2,
  avatar_kind: "initials",
  csrf_token: "csrf",
  default_landing_page: "manage",
  display_name: "Owner",
  role: "owner",
  theme_key: "warm-paper",
  user_id: 1,
} satisfies ClientUser

const member = {
  ...owner,
  role: "user",
} satisfies ClientUser

const admin = {
  ...owner,
  role: "admin",
} satisfies ClientUser

const redirects = vi.hoisted(() => ({ assign: vi.fn() }))
const roomFixture = [{ id: "local-nest", name: "Local Nest", desired_bed_count: 4, beds: [] }]

function setSession(user: ClientUser | null, loading = false): void {
  vi.mocked(useSession).mockReturnValue({
    loading,
    refresh: vi.fn(async () => undefined),
    refreshCsrfToken: vi.fn(async () => user?.csrf_token ?? ""),
    user,
  })
}

function renderMonitor(locale: SupportedLocale = "zh-CN") {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  return render(<I18nextProvider i18n={instance}><MonitorPage /></I18nextProvider>)
}

describe("MonitorPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal("location", { assign: redirects.assign })
    vi.mocked(ownerRooms).mockResolvedValue(roomFixture)
    setSession(owner)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("fills the product viewport with the shared observation monitor for an Owner", async () => {
    const { container } = renderMonitor()

    expect(container.querySelector("main")).toHaveClass("monitor-page")
    expect(await screen.findByRole("region", { name: "房间 3D 观察" })).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "房间 3D 观察" })).toHaveAttribute("data-bed-count", "4")
    expect(screen.queryByRole("heading")).toBeNull()
    expect(redirects.assign).not.toHaveBeenCalled()
  })

  it("shows the monitor rail and hides it when immersive mode is entered", async () => {
    const user = userEvent.setup()
    renderMonitor()

    expect(screen.getByRole("link", { name: "进入管理" })).toHaveAttribute("href", "/manage")
    expect(screen.getByRole("link", { name: "进入聊天" })).toHaveAttribute("href", "/chat")
    expect(screen.getByRole("button", { name: "进入沉浸观察" })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "进入沉浸观察" }))

    expect(screen.queryByRole("link", { name: "进入管理" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "进入沉浸观察" })).not.toBeInTheDocument()
    expect(screen.getByRole("region", { name: "房间 3D 观察" })).toBeInTheDocument()
  })

  it("fills the product viewport for an Admin", async () => {
    setSession(admin)

    renderMonitor()

    expect(await screen.findByRole("region", { name: "房间 3D 观察" })).toBeInTheDocument()
    expect(redirects.assign).not.toHaveBeenCalled()
  })

  it("keeps the session-verification state out of the monitor surface", () => {
    setSession(null, true)

    renderMonitor()

    expect(screen.getByText("正在验证会话…")).toBeInTheDocument()
    expect(document.querySelector("[data-slot='observation-monitor']")).toBeNull()
    expect(redirects.assign).not.toHaveBeenCalled()
  })

  it("redirects an anonymous client-side navigation to login with the monitor return path", () => {
    setSession(null)

    renderMonitor()

    expect(redirects.assign).toHaveBeenCalledWith("/login?next=/monitor")
    expect(document.querySelector("[data-slot='observation-monitor']")).toBeNull()
  })

  it("renders the read-only monitor for an ordinary signed-in user", async () => {
    setSession(member)

    renderMonitor()

    expect(await screen.findByRole("region", { name: "房间 3D 观察" })).toBeInTheDocument()
    expect(redirects.assign).not.toHaveBeenCalled()
  })

  it("shows the localized session status in English without changing authorization redirects", () => {
    // Given: an English client is still waiting for the Owner session check.
    setSession(null, true)

    // When: the real monitor route renders.
    renderMonitor("en-US")

    // Then: only the localized status is visible and the route is not redirected.
    expect(screen.getByText("Verifying your session…")).toBeInTheDocument()
    expect(document.querySelector("[data-slot='observation-monitor']")).toBeNull()
    expect(redirects.assign).not.toHaveBeenCalled()
  })
})
