import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { configureDiscordAccount, createDiscordPairingSession, disconnectDiscordAccount, type DiscordAccount } from "../../api/client"
import { createI18n } from "../../i18n/config"
import { ProfileDiscordAccount } from "./ProfileDiscordAccount"

vi.mock("../../api/client", () => ({
  configureDiscordAccount: vi.fn(),
  createDiscordPairingSession: vi.fn(),
  disconnectDiscordAccount: vi.fn(),
}))

const unconfigured = {
  elfie_id: "00000001",
  state: "unconfigured" as const,
  bot_username: null,
  bot_display_name: null,
  bound_discord_username: null,
  bound_display_name: null,
  last_checked_at: null,
  issue: null,
}

const waiting = {
  ...unconfigured,
  state: "waiting_pairing" as const,
  bot_username: "elfienest_star",
  bot_display_name: "星星",
  last_checked_at: "2026-08-16T01:00:00.000Z",
}

describe("ProfileDiscordAccount", () => {
  beforeEach(() => vi.clearAllMocks())

  function renderDiscord(account: DiscordAccount = unconfigured, overrides: Partial<React.ComponentProps<typeof ProfileDiscordAccount>> = {}) {
    return render(<I18nextProvider i18n={createI18n()}><ProfileDiscordAccount account={account} csrfToken="csrf" elfieId="00000001" onAccountChange={vi.fn()} {...overrides} /></I18nextProvider>)
  }

  it("keeps setup novice-friendly and does not ask for a server permission", async () => {
    const user = userEvent.setup()
    renderDiscord()
    await user.click(screen.getByRole("button", { name: "连接 Discord" }))

    expect(screen.getByRole("heading", { name: "连接 Discord" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Discord Developer Portal/ })).toHaveAttribute("href", "https://discord.com/developers/applications")
    expect(screen.getByText(/保持默认权限/)).toBeInTheDocument()
  })

  it("validates a token, creates a pairing code, and keeps the secret out of the UI", async () => {
    const user = userEvent.setup()
    const onRefresh = vi.fn().mockResolvedValue(undefined)
    vi.mocked(configureDiscordAccount).mockResolvedValue(waiting)
    vi.mocked(createDiscordPairingSession).mockResolvedValue({
      invite_url: "https://discord.com/oauth2/authorize?client_id=991",
      bot_profile_url: "https://discord.com/users/991",
      pairing_code: "pairing-code",
      expires_at: "2026-08-16T01:10:00.000Z",
    })
    renderDiscord(unconfigured, { onRefresh })

    await user.click(screen.getByRole("button", { name: "连接 Discord" }))
    await user.click(screen.getByRole("button", { name: "下一步" }))
    await user.type(screen.getByPlaceholderText("粘贴 Discord Bot Token"), "discord-secret-token")
    await user.click(screen.getByRole("button", { name: "验证并继续" }))

    expect(configureDiscordAccount).toHaveBeenCalledWith("00000001", "discord-secret-token", "csrf")
    expect(createDiscordPairingSession).toHaveBeenCalledWith("00000001", "csrf")
    expect(await screen.findByRole("link", { name: "安装机器人" })).toHaveAttribute("href", expect.stringContaining("discord.com/oauth2"))
    expect(screen.getByRole("link", { name: "打开 Discord" })).toHaveClass("profile-private-discord__open-button")
    expect(screen.getByText("pairing-code")).toBeInTheDocument()
    expect(screen.queryByText("discord-secret-token")).not.toBeInTheDocument()
    await waitFor(() => expect(onRefresh).toHaveBeenCalled())
  })

  it("does not show owner actions without the csrf boundary", () => {
    render(<I18nextProvider i18n={createI18n()}><ProfileDiscordAccount account={{ ...waiting, state: "active", bound_discord_username: "owner_seven", bound_display_name: "七号主人" }} elfieId="00000001" /></I18nextProvider>)
    expect(screen.queryByRole("button", { name: "更多操作" })).not.toBeInTheDocument()
    expect(disconnectDiscordAccount).not.toHaveBeenCalled()
  })

  it("keeps the active more action compact like Telegram", () => {
    renderDiscord({ ...waiting, state: "active", bound_discord_username: "owner_seven", bound_display_name: "七号主人" })

    const moreButton = screen.getByRole("button", { name: "更多操作" })
    expect(moreButton.closest(".profile-private-discord__actions")).not.toBeNull()
  })
})
