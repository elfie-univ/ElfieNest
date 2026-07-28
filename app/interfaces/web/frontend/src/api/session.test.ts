import { describe, expect, it, vi } from "vitest"

import { currentUser } from "./session"
import { requestJson } from "./http"

vi.mock("./http", () => ({
  csrfHeaders: vi.fn(),
  requestJson: vi.fn(),
}))

describe("session API", () => {
  it("loads the current user from the session endpoint", async () => {
    vi.mocked(requestJson).mockResolvedValueOnce({
      id: 1,
      username: "owner",
      role: "owner",
      nickname: null,
      avatar_url: null,
      avatar_color: 0,
      avatar_kind: "initials",
      default_landing_page: "manage",
      theme_key: "warm-paper",
      csrf_token: "csrf",
    })

    await expect(currentUser()).resolves.toMatchObject({
      username: "owner",
      role: "owner",
      csrf_token: "csrf",
    })
    expect(requestJson).toHaveBeenCalledWith("/session/current.json")
  })
})
