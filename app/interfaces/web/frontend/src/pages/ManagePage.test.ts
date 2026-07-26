import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("ManagePage", () => {
  it("does not keep the account default-login preference inside the monitor panel", () => {
    const source = readFileSync(resolve(import.meta.dirname, "ManagePage.tsx"), "utf8")

    expect(source).not.toContain('title="默认打开页面"')
    expect(source).not.toContain("saveLandingPage")
  })

  it("renders one page title without the repeated eyebrow and fixed Owner subtitle", () => {
    const source = readFileSync(resolve(import.meta.dirname, "ManagePage.tsx"), "utf8")

    expect(source).not.toContain('<p className="brand">')
    expect(source).not.toContain("管理、聊天与领养保持分离")
    expect(source.match(/<h1>/g)).toHaveLength(1)
  })

  it("uses the documented ElfieNest logo in the manage sidebar", () => {
    const source = readFileSync(resolve(import.meta.dirname, "../components/ManageSidebar.tsx"), "utf8")

    expect(source).toContain("docs/public/assets/logo.png")
    expect(source).toContain('<img alt="ElfieNest"')
    expect(source).toContain("管理系统")
  })

  it("does not repeat page titles inside reachable panel content", () => {
    const managePage = readFileSync(resolve(import.meta.dirname, "ManagePage.tsx"), "utf8")
    const systemSettings = readFileSync(resolve(import.meta.dirname, "../components/SystemSettingsPanel.tsx"), "utf8")

    expect(managePage).not.toContain("<h2>工具与权限</h2>")
    expect(systemSettings).not.toContain("<h2>系统设置</h2>")
  })
})
