import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { beforeAll, describe, expect, it, vi } from "vitest"

import { AccountMenu, AccountMenuPanel } from "./AccountMenu"

const owner = {
  account_id: "admin123",
  avatar_color: 2,
  avatar_kind: "initials" as const,
  csrf_token: "test-token",
  default_landing_page: "manage" as const,
  nickname: "阿尔法",
  role: "owner" as const,
  theme_key: "warm-paper" as const,
  username: "admin123",
}

describe("AccountMenu", () => {
  beforeAll(() => {
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
  })

  it("keeps the account panel open while choosing a portal-rendered landing page", async () => {
    const user = userEvent.setup()
    render(<AccountMenu onUpdated={async () => undefined} user={owner} />)

    await user.click(screen.getByRole("button", { name: /阿尔法/ }))
    await user.click(screen.getByRole("button", { name: /默认登录页/ }))
    await user.click(screen.getByRole("combobox", { name: "默认登录页" }))
    await user.click(await screen.findByRole("option", { name: "聊天页" }))

    expect(screen.getByRole("region", { name: "个人与外观设置" })).toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: "默认登录页" })).toHaveTextContent("聊天页")
  })

  it("renders display-first identity information with only the local avatar upload control", () => {
    const html = renderToStaticMarkup(createElement(AccountMenuPanel, { onClose: () => undefined, onUpdated: async () => undefined, user: owner }))

    expect(html).toContain("阿尔法")
    expect(html).toContain("@admin123")
    expect(html).toContain('aria-label="上传本地头像"')
    expect(html).not.toContain('aria-label="显示名称"')
    expect(html).not.toContain("select-field__trigger")
  })
})
