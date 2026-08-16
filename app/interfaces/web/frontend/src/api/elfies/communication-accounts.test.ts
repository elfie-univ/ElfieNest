import { beforeEach, describe, expect, it, vi } from "vitest"

import { ownerWrite, requestJson } from "../http"
import {
  configureDiscordAccount,
  createDiscordPairingSession,
  discordAccount,
  disconnectDiscordAccount,
  configureTelegramAccount,
  createTelegramPairingSession,
  disconnectTelegramAccount,
  telegramAccount,
} from "./communication-accounts"

vi.mock("../http", () => ({ ownerWrite: vi.fn(), requestJson: vi.fn() }))

const account = {
  elfie_id: "00000001",
  state: "waiting_pairing",
  bot_username: "elfienest_star_bot",
  bot_display_name: "星星",
  bound_telegram_username: null,
  bound_display_name: null,
  last_checked_at: "2026-08-16T01:00:00.000Z",
  issue: null,
}

const discordAccountValue = {
  elfie_id: "00000001",
  state: "waiting_pairing",
  bot_username: "elfienest_star",
  bot_display_name: "星星",
  bound_discord_username: null,
  bound_display_name: null,
  last_checked_at: "2026-08-16T01:00:00.000Z",
  issue: null,
}

describe("versioned Elfie Telegram account client", () => {
  beforeEach(() => vi.clearAllMocks())

  it("uses only the nested owner-scoped resource and never reads a token", async () => {
    vi.mocked(requestJson).mockResolvedValue(account)
    vi.mocked(ownerWrite)
      .mockResolvedValueOnce(account)
      .mockResolvedValueOnce({ deep_link: "https://t.me/bot?start=opaque", expires_at: "t1" })
      .mockResolvedValueOnce({ ...account, state: "unconfigured", bot_username: null, bot_display_name: null, last_checked_at: null })

    await telegramAccount("00000001")
    await configureTelegramAccount("00000001", "991:secret", "csrf")
    await createTelegramPairingSession("00000001", "csrf")
    await disconnectTelegramAccount("00000001", "csrf")

    const root = "/api/v1/elfies/00000001/communication-accounts/telegram"
    expect(requestJson).toHaveBeenCalledWith(root)
    expect(ownerWrite).toHaveBeenNthCalledWith(1, root, "PUT", "csrf", { bot_token: "991:secret" })
    expect(ownerWrite).toHaveBeenNthCalledWith(2, `${root}/pairing-sessions`, "POST", "csrf")
    expect(ownerWrite).toHaveBeenNthCalledWith(3, root, "DELETE", "csrf")
  })

  it("rejects a response that attempts to return the secret", async () => {
    vi.mocked(requestJson).mockResolvedValue({ ...account, bot_token: "leak" })
    await expect(telegramAccount("00000001")).rejects.toThrow()
  })
})

describe("versioned Elfie Discord account client", () => {
  beforeEach(() => vi.clearAllMocks())

  it("uses the nested Discord resource and keeps the token out of response parsing", async () => {
    vi.mocked(requestJson).mockResolvedValue(discordAccountValue)
    vi.mocked(ownerWrite)
      .mockResolvedValueOnce(discordAccountValue)
      .mockResolvedValueOnce({
        invite_url: "https://discord.com/oauth2/authorize?client_id=1",
        bot_profile_url: "https://discord.com/users/1",
        pairing_code: "pairing-code",
        expires_at: "t1",
      })
      .mockResolvedValueOnce({ ...discordAccountValue, state: "unconfigured", bot_username: null, bot_display_name: null, last_checked_at: null })

    await discordAccount("00000001")
    await configureDiscordAccount("00000001", "discord-secret-token", "csrf")
    await createDiscordPairingSession("00000001", "csrf")
    await disconnectDiscordAccount("00000001", "csrf")

    const root = "/api/v1/elfies/00000001/communication-accounts/discord"
    expect(requestJson).toHaveBeenCalledWith(root)
    expect(ownerWrite).toHaveBeenNthCalledWith(1, root, "PUT", "csrf", { bot_token: "discord-secret-token" })
    expect(ownerWrite).toHaveBeenNthCalledWith(2, `${root}/pairing-sessions`, "POST", "csrf")
    expect(ownerWrite).toHaveBeenNthCalledWith(3, root, "DELETE", "csrf")
  })

  it("rejects a response that attempts to return the Discord secret", async () => {
    vi.mocked(requestJson).mockResolvedValue({ ...discordAccountValue, bot_token: "leak" })
    await expect(discordAccount("00000001")).rejects.toThrow()
  })
})
