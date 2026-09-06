import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"

import type { ClientUser } from "../api/client"
import { createI18n } from "../i18n/config"
import { ChatRail } from "./ChatRail"

const owner = {
  account_id: "owner",
  avatar_color: 2,
  avatar_kind: "initials",
  csrf_token: "csrf",
  default_landing_page: "chat",
  display_name: "Owner",
  role: "owner",
  theme_key: "warm-paper",
  user_id: 1,
} as const satisfies ClientUser

const member = { ...owner, role: "user" } as const satisfies ClientUser
const admin = { ...owner, role: "admin" } as const satisfies ClientUser

function renderRail(user: ClientUser): void {
  const instance = createI18n()
  void instance.changeLanguage("zh-CN")
  render(
    <I18nextProvider i18n={instance}>
      <ChatRail
        activePane="elfies"
        onMobileAccess={vi.fn()}
        onOpenSection={vi.fn()}
        onUpdated={async () => undefined}
        user={user}
      />
    </I18nextProvider>,
  )
}

describe("ChatRail", () => {
  it("shows management and monitor links for an Owner", () => {
    // Given: an authenticated Owner on the chat surface.
    renderRail(owner)

    // When: the chat rail is rendered.
    const monitorLink = screen.getByRole("link", { name: "进入监控" })

    // Then: both Owner-only destinations are available and monitor uses the CCTV icon.
    expect(screen.getByRole("link", { name: "进入管理" })).toHaveAttribute("href", "/manage")
    expect(monitorLink).toHaveAttribute("href", "/monitor")
    expect(monitorLink.querySelector("svg")).toHaveClass("lucide-cctv")
  })

  it("hides management but keeps the read-only monitor link for an ordinary user", () => {
    // Given: an authenticated ordinary user.
    renderRail(member)

    // When: the chat rail is rendered.
    // Then: management stays restricted while the read-only monitor remains available.
    expect(screen.queryByRole("link", { name: "进入管理" })).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: "进入监控" })).toHaveAttribute("href", "/monitor")
  })

  it("shows management and monitor links for an Admin", () => {
    renderRail(admin)

    expect(screen.getByRole("link", { name: "进入管理" })).toHaveAttribute("href", "/manage")
    expect(screen.getByRole("link", { name: "进入监控" })).toHaveAttribute("href", "/monitor")
  })
})
