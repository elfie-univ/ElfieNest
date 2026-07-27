import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

import { AccountMenuPanel } from "./AccountMenu"

const owner = {
  avatar_color: 2,
  avatar_kind: "initials" as const,
  csrf_token: "test-token",
  default_landing_page: "manage" as const,
  id: 7,
  nickname: "阿尔法",
  role: "owner" as const,
  theme_key: "warm-paper" as const,
  username: "admin123",
}

describe("AccountMenu", () => {
  it("keeps Radix portal selections within the account-menu click boundary", () => {
    const source = readFileSync(resolve(import.meta.dirname, "AccountMenu.tsx"), "utf8")

    expect(source).toContain('closest(".select-field__content")')
  })

  it("renders display-first identity information with only the local avatar upload control", () => {
    const html = renderToStaticMarkup(createElement(AccountMenuPanel, { onClose: () => undefined, onUpdated: async () => undefined, user: owner }))

    expect(html).toContain("阿尔法")
    expect(html).toContain("ID: 7")
    expect(html).toContain('aria-label="上传本地头像"')
    expect(html).not.toContain('aria-label="显示名称"')
    expect(html).not.toContain("select-field__trigger")
  })
})
