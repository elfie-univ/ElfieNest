import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  configureTelegramAccount,
  createTelegramPairingSession,
  disconnectTelegramAccount,
} from "../../api/client"
import { createI18n } from "../../i18n/config"
import { ProfileTelegramAccount } from "./ProfileTelegramAccount"

vi.mock("../../api/client", () => ({
  configureTelegramAccount: vi.fn(),
  createTelegramPairingSession: vi.fn(),
  disconnectTelegramAccount: vi.fn(),
}))

const unconfigured = {
  elfie_id: "00000001",
  state: "unconfigured" as const,
  bot_username: null,
  bot_display_name: null,
  bound_telegram_username: null,
  bound_display_name: null,
  last_checked_at: null,
  issue: null,
}

const active = {
  elfie_id: "00000001",
  state: "active" as const,
  bot_username: "elfienest_star_bot",
  bot_display_name: "星星",
  bound_telegram_username: "owner_seven",
  bound_display_name: "七号主人",
  last_checked_at: "2026-08-16T01:00:00.000Z",
  issue: null,
}

const waiting = {
  ...active,
  state: "waiting_pairing" as const,
  bound_telegram_username: null,
  bound_display_name: null,
}

function renderTelegram(
  account: typeof unconfigured | typeof active | typeof waiting = unconfigured,
  overrides: Partial<React.ComponentProps<typeof ProfileTelegramAccount>> = {},
) {
  return render(
    <I18nextProvider i18n={createI18n()}>
      <ProfileTelegramAccount
        account={account}
        csrfToken="csrf"
        elfieId="00000001"
        elfieName="星星"
        onAccountChange={vi.fn()}
        {...overrides}
      />
    </I18nextProvider>,
  )
}

describe("ProfileTelegramAccount", () => {
  const writeText = vi.fn().mockResolvedValue(undefined)

  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    })
  })

  it("keeps the first page short and makes BotFather, /newbot, and the suggested username directly actionable", async () => {
    const user = userEvent.setup()
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    })
    renderTelegram()

    await user.click(screen.getByRole("button", { name: "连接 Telegram" }))

    expect(screen.getByRole("heading", { name: "连接 Telegram" })).toBeInTheDocument()
    expect(screen.queryByText(/第 1 步|跟着下面三步|先在 Telegram 创建机器人/)).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: "@BotFather" })).toHaveAttribute("href", "https://t.me/BotFather")
    expect(screen.getByText("看到 BotFather 返回 Token，即创建成功")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "复制 /newbot" }))
    expect(writeText).toHaveBeenCalledWith("/newbot")
    await user.click(screen.getByRole("button", { name: "复制 elfie_000001_bot" }))
    expect(writeText).toHaveBeenCalledWith("elfie_000001_bot")
  })

  it("supports going back on every setup page", async () => {
    const user = userEvent.setup()
    renderTelegram()

    await user.click(screen.getByRole("button", { name: "连接 Telegram" }))
    await user.click(screen.getByRole("button", { name: "下一步" }))
    expect(screen.getByText("Token", { selector: "label" })).toBeInTheDocument()
    expect(screen.getByPlaceholderText("粘贴 BotFather 返回的 Token")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "返回" }))
    expect(screen.getByRole("link", { name: "@BotFather" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "返回" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("validates the Token, creates the binding link automatically, and never renders the Token back", async () => {
    const user = userEvent.setup()
    const onAccountChange = vi.fn()
    const onRefresh = vi.fn().mockResolvedValue(undefined)
    const configured = { ...waiting, bot_username: "elfienest_star_bot" }
    vi.mocked(configureTelegramAccount).mockResolvedValue(configured)
    vi.mocked(createTelegramPairingSession).mockResolvedValue({
      deep_link: "https://t.me/elfienest_star_bot?start=opaque",
      expires_at: "2026-08-16T01:10:00.000Z",
    })
    renderTelegram(unconfigured, { onAccountChange, onRefresh })

    await user.click(screen.getByRole("button", { name: "连接 Telegram" }))
    await user.click(screen.getByRole("button", { name: "下一步" }))
    const token = screen.getByPlaceholderText("粘贴 BotFather 返回的 Token")
    await user.type(token, "991:secret-token-value")
    expect(screen.queryByRole("button", { name: "粘贴" })).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "验证并继续" }))

    expect(configureTelegramAccount).toHaveBeenCalledWith("00000001", "991:secret-token-value", "csrf")
    expect(createTelegramPairingSession).toHaveBeenCalledWith("00000001", "csrf")
    expect(onAccountChange).toHaveBeenCalledWith(configured)
    expect(await screen.findByRole("link", { name: "打开 Telegram" })).toHaveAttribute(
      "href",
      "https://t.me/elfienest_star_bot?start=opaque",
    )
    expect(screen.getByText("等待你的 Telegram 账号")).toBeInTheDocument()
    expect(screen.queryByText(/secret-token-value/)).not.toBeInTheDocument()
    await waitFor(() => expect(onRefresh).toHaveBeenCalled())

    await user.click(screen.getByRole("button", { name: "返回" }))
    expect(screen.getByPlaceholderText("粘贴 BotFather 返回的 Token")).toBeInTheDocument()
  })

  it("continues an unfinished binding without asking the owner to generate a link", async () => {
    const user = userEvent.setup()
    vi.mocked(createTelegramPairingSession).mockResolvedValue({
      deep_link: "https://t.me/elfienest_star_bot?start=opaque",
      expires_at: "2026-08-16T01:10:00.000Z",
    })
    renderTelegram(waiting)

    await user.click(screen.getByRole("button", { name: "继续绑定" }))

    expect(createTelegramPairingSession).toHaveBeenCalledWith("00000001", "csrf")
    expect(await screen.findByRole("link", { name: "打开 Telegram" })).toHaveAttribute(
      "href",
      "https://t.me/elfienest_star_bot?start=opaque",
    )
    expect(screen.queryByRole("button", { name: "生成配对链接" })).not.toBeInTheDocument()
  })

  it("shows the connected bot and owner, with secondary actions in one overflow menu", async () => {
    const user = userEvent.setup()
    renderTelegram(active)

    expect(screen.getByText("星星")).toBeInTheDocument()
    expect(screen.getByText("@elfienest_star_bot")).toBeInTheDocument()
    expect(screen.getByText("七号主人")).toBeInTheDocument()
    expect(screen.getByText("@owner_seven")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "打开 Telegram" })).toHaveAttribute(
      "href",
      "https://t.me/elfienest_star_bot",
    )
    expect(screen.queryByRole("button", { name: "刷新状态" })).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "更多操作" }))
    await user.click(screen.getByRole("menuitem", { name: "重新配置" }))
    expect(screen.getByPlaceholderText("粘贴 BotFather 返回的 Token")).toBeInTheDocument()
  })

  it("does not replace an active binding or create a new pairing link until a new Token validates", async () => {
    const user = userEvent.setup()
    const onAccountChange = vi.fn()
    vi.mocked(configureTelegramAccount).mockResolvedValue(active)
    renderTelegram(active, { onAccountChange })

    await user.click(screen.getByRole("button", { name: "更多操作" }))
    await user.click(screen.getByRole("menuitem", { name: "重新配置" }))
    await user.type(screen.getByPlaceholderText("粘贴 BotFather 返回的 Token"), "991:new-secret-token")
    await user.click(screen.getByRole("button", { name: "验证并继续" }))

    expect(onAccountChange).toHaveBeenCalledWith(active)
    expect(createTelegramPairingSession).not.toHaveBeenCalled()
    expect(screen.getByText("绑定完成，可以聊天了")).toBeInTheDocument()
  })

  it("does not expose owner controls when the csrf boundary is absent", () => {
    render(
      <I18nextProvider i18n={createI18n()}>
        <ProfileTelegramAccount account={active} elfieId="00000001" elfieName="星星" />
      </I18nextProvider>,
    )

    expect(screen.queryByRole("button", { name: "更多操作" })).not.toBeInTheDocument()
    expect(disconnectTelegramAccount).not.toHaveBeenCalled()
  })

  it("does not present setup controls when reading the account fails", async () => {
    const user = userEvent.setup()
    const onRefresh = vi.fn().mockResolvedValue(undefined)
    render(
      <I18nextProvider i18n={createI18n()}>
        <ProfileTelegramAccount
          account={null}
          accountError="配置读取失败"
          csrfToken="csrf"
          elfieId="00000001"
          elfieName="星星"
          onRefresh={onRefresh}
        />
      </I18nextProvider>,
    )

    expect(screen.getByRole("alert")).toHaveTextContent("配置读取失败")
    expect(screen.queryByPlaceholderText("粘贴 BotFather 返回的 Token")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "重试" }))
    expect(onRefresh).toHaveBeenCalledOnce()
  })
})
