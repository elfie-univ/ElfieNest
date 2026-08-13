import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"

import type { ClientUser } from "../api/client"
import { createI18n } from "../i18n/config"
import { MonitorRail } from "./MonitorRail"

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
} as const satisfies ClientUser

function renderRail() {
  const instance = createI18n()
  void instance.changeLanguage("zh-CN")
  const onToggleImmersive = vi.fn()
  render(<I18nextProvider i18n={instance}><MonitorRail onMobileAccess={vi.fn()} onToggleImmersive={onToggleImmersive} onUpdated={async () => undefined} user={owner} /></I18nextProvider>)
  return { onToggleImmersive }
}

describe("MonitorRail", () => {
  it("keeps navigation and account actions in the chat-style rail", async () => {
    const user = userEvent.setup()
    const { onToggleImmersive } = renderRail()

    expect(screen.getByRole("link", { name: "进入管理" })).toHaveAttribute("href", "/manage")
    expect(screen.getByRole("link", { name: "进入聊天" })).toHaveAttribute("href", "/chat")
    expect(screen.getByRole("button", { name: "扫码用手机打开监控" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "进入沉浸观察" })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "进入沉浸观察" }))

    expect(onToggleImmersive).toHaveBeenCalledOnce()
  })
})
