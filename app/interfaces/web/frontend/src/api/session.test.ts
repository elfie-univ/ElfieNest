import { describe, expect, it, vi } from "vitest"

import { requestJson } from "./http"
import { currentUser, login, safeLoginNextPath } from "./session"

vi.mock("./http", () => ({ requestJson: vi.fn() }))

describe("currentUser", () => {
  it("uses the server username as the business account identifier when account_id is absent", async () => {
    vi.mocked(requestJson).mockResolvedValue({
      id: 1,
      username: "admin123",
      role: "owner",
      nickname: "admin123",
      avatar_color: 0,
      avatar_kind: "initials",
      avatar_url: null,
      default_landing_page: "manage",
      theme_key: "warm-paper",
      created_at: "2026-07-28 03:25:24",
      elfie_count: 0,
      csrf_token: "csrf-token",
    })

    await expect(currentUser()).resolves.toMatchObject({
      account_id: "admin123",
      username: "admin123",
      role: "owner",
    })
  })
})

describe("safe login destinations", () => {
  it("accepts only known local product pages", () => {
    expect(safeLoginNextPath("/chat")).toBe("/chat")
    expect(safeLoginNextPath("/manage")).toBe("/manage")
    expect(safeLoginNextPath("/monitor")).toBe("/monitor")
    expect(safeLoginNextPath("https://attacker.invalid")).toBe("")
    expect(safeLoginNextPath("//attacker.invalid")).toBe("")
    expect(safeLoginNextPath("/monitor?mode=unexpected")).toBe("")
  })

  it("sends and accepts the Owner monitor return destination", async () => {
    vi.mocked(requestJson).mockResolvedValue({ landing_path: "/monitor" })

    await expect(login("owner", "pass123", "/monitor")).resolves.toBe("/monitor")

    expect(requestJson).toHaveBeenCalledWith(
      "/api/auth/login?next=/monitor",
      expect.objectContaining({ method: "POST" }),
    )
  })
})
