import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("ChatPage rail", () => {
  it("labels every icon-only desktop rail action with a visible tooltip contract", () => {
    const source = readFileSync(resolve(import.meta.dirname, "ChatPage.tsx"), "utf8")

    expect(source).toContain('data-tooltip="聊天记录"')
    expect(source).toContain('data-tooltip="我的精灵"')
    expect(source).toContain('data-tooltip="进入管理"')
    expect(source).toContain('data-tooltip="扫码用手机打开聊天"')
  })
})
