import { beforeEach, describe, expect, it, vi } from "vitest"

import { requestJson } from "./http"
import { currentUser, login, safeLoginNextPath, setup, updateProfile } from "./session"

vi.mock("./http", () => ({
  csrfHeaders: vi.fn(() => ({ "Content-Type": "application/json", "X-CSRF-Token": "csrf-token" })),
  requestJson: vi.fn(),
}))

beforeEach(() => {
  vi.clearAllMocks()
})

describe("currentUser", () => {
  it("parses the canonical current-user contract without synthesizing aliases", async () => {
    // Given: the authenticated endpoint returns only canonical account fields.
    vi.mocked(requestJson).mockResolvedValue({
      user_id: 1,
      account_id: "admin123",
      display_name: "Owner",
      gender: "male",
      birth_date: null,
      role: "owner",
      avatar_color: 0,
      avatar_kind: "initials",
      avatar_url: null,
      default_landing_page: "manage",
      theme_key: "warm-paper",
      created_at: "2026-07-28 03:25:24",
      elfie_count: 0,
      csrf_token: "csrf-token",
    })

    // When: the untrusted response crosses the session boundary.
    const user = await currentUser()

    // Then: identity remains canonical and no legacy aliases are created.
    expect(user).toMatchObject({
      user_id: 1,
      account_id: "admin123",
      display_name: "Owner",
      role: "owner",
    })
    expect(user).not.toHaveProperty("id")
    expect(user).not.toHaveProperty("username")
    expect(user).not.toHaveProperty("nickname")
  })

  it.each([
    { id: 1, nickname: "Owner", role: "owner", username: "admin123" },
    { account_id: "admin123", display_name: null, role: "owner", user_id: "1" },
    { account_id: "admin123", role: "owner", user_id: 1 },
  ])("rejects a legacy or malformed payload %#", async (payload) => {
    // Given: the endpoint omits or mistypes a required canonical field.
    vi.mocked(requestJson).mockResolvedValue(payload)

    // When/Then: the client rejects it instead of normalizing an alias.
    await expect(currentUser()).rejects.toThrow()
  })
})

describe("canonical account requests", () => {
  it("sends account_id and display_name during setup without an account locale", async () => {
    // Given: setup returns the final identity contract.
    vi.mocked(requestJson).mockResolvedValue({
      account_id: "owner01",
      csrf_token: "csrf-token",
      display_name: "Owner",
      role: "owner",
      user_id: 1,
    })

    // When: the owner form is submitted.
    await setup("owner01", "secret-pass", "Owner")

    // Then: only canonical account/profile fields are sent.
    expect(requestJson).toHaveBeenCalledWith("/api/auth/setup", expect.objectContaining({
      body: JSON.stringify({ account_id: "owner01", display_name: "Owner", password: "secret-pass" }),
      method: "POST",
    }))
  })

  it("sends account_id in the login form body", async () => {
    // Given: the server accepts a canonical login and chooses chat.
    vi.mocked(requestJson).mockResolvedValue({ landing_path: "/chat" })

    // When: a user signs in.
    await login("owner01", "secret-pass", "/chat")

    // Then: the form body contains account_id rather than a legacy alias.
    expect(requestJson).toHaveBeenCalledWith("/api/auth/login?next=/chat", expect.objectContaining({ method: "POST" }))
    const requestBody = vi.mocked(requestJson).mock.calls[0]?.[1]?.body
    expect(requestBody).toBeInstanceOf(URLSearchParams)
    if (!(requestBody instanceof URLSearchParams)) throw new TypeError("expected URLSearchParams login body")
    expect(requestBody.get("account_id")).toBe("owner01")
    expect(requestBody.get("username")).toBeNull()
    expect(requestBody.get("password")).toBe("secret-pass")
  })

  it("sends display_name for profile updates", async () => {
    // Given: the profile endpoint accepts an empty response body.
    vi.mocked(requestJson).mockResolvedValue({})

    // When: the display name is changed.
    await updateProfile({ display_name: "Owner Renamed" }, "csrf-token")

    // Then: the request contains no nickname alias.
    expect(requestJson).toHaveBeenCalledWith("/api/auth/me/profile", expect.objectContaining({
      body: JSON.stringify({ display_name: "Owner Renamed" }),
      method: "PUT",
    }))
  })

  it("sends the editable identity projection for profile updates", async () => {
    vi.mocked(requestJson).mockResolvedValue({})

    await updateProfile({
      account_id: "owner-renamed",
      birth_date: "1990-02-03",
      display_name: "Owner Renamed",
      gender: "female",
    }, "csrf-token")

    expect(requestJson).toHaveBeenCalledWith("/api/auth/me/profile", expect.objectContaining({
      body: JSON.stringify({
        account_id: "owner-renamed",
        birth_date: "1990-02-03",
        display_name: "Owner Renamed",
        gender: "female",
      }),
      method: "PUT",
    }))
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
