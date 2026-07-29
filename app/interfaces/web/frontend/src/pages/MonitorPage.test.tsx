import { render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { ClientUser } from "../api/client"
import { useSession } from "../stores/session"
import { MonitorPage } from "./MonitorPage"

vi.mock("../stores/session", () => ({ useSession: vi.fn() }))

vi.mock("../components/ObservationMonitor", () => ({
  ObservationMonitor: ({ roomId }: { readonly roomId: string }) => <section aria-label="房间 3D 观察" data-room-id={roomId} data-slot="observation-monitor" role="region" />,
}))

const owner = {
  account_id: "owner",
  avatar_color: 2,
  avatar_kind: "initials",
  csrf_token: "csrf",
  default_landing_page: "manage",
  nickname: "Owner",
  role: "owner",
  theme_key: "warm-paper",
  username: "owner",
} satisfies ClientUser

const member = {
  ...owner,
  role: "user",
} satisfies ClientUser

const redirects = vi.hoisted(() => ({ assign: vi.fn() }))

function setSession(user: ClientUser | null, loading = false): void {
  vi.mocked(useSession).mockReturnValue({ loading, refresh: vi.fn(async () => undefined), user })
}

describe("MonitorPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal("location", { assign: redirects.assign })
    setSession(owner)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("fills the product viewport with the shared observation monitor for an Owner", () => {
    const { container } = render(<MonitorPage />)

    expect(container.querySelector("main")).toHaveClass("monitor-page")
    expect(container.querySelectorAll("[data-slot='observation-monitor']")).toHaveLength(1)
    expect(screen.getByRole("region", { name: "房间 3D 观察" })).toBeInTheDocument()
    expect(screen.queryByRole("heading")).toBeNull()
    expect(redirects.assign).not.toHaveBeenCalled()
  })

  it("keeps the session-verification state out of the monitor surface", () => {
    setSession(null, true)

    render(<MonitorPage />)

    expect(screen.getByText("正在验证会话…")).toBeInTheDocument()
    expect(screen.queryByRole("region", { name: "房间 3D 观察" })).toBeNull()
    expect(redirects.assign).not.toHaveBeenCalled()
  })

  it("redirects an anonymous client-side navigation to login with the monitor return path", () => {
    setSession(null)

    render(<MonitorPage />)

    expect(redirects.assign).toHaveBeenCalledWith("/login?next=/monitor")
    expect(screen.queryByRole("region", { name: "房间 3D 观察" })).toBeNull()
  })

  it("redirects an ordinary client-side navigation to chat", () => {
    setSession(member)

    render(<MonitorPage />)

    expect(redirects.assign).toHaveBeenCalledWith("/chat")
    expect(screen.queryByRole("region", { name: "房间 3D 观察" })).toBeNull()
  })
})
