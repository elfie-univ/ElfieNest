import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  createManagedUser,
  deleteManagedUser,
  ownerUsers,
  resetManagedUserPassword,
  updateManagedUser,
} from "./owner-users"
import { ownerWrite, requestJson } from "./http"

vi.mock("./http", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("./http")>()
  return {
    ...original,
    ownerWrite: vi.fn(),
    requestJson: vi.fn(),
  }
})

const member = {
  user_id: 7,
  account_id: "member01",
  display_name: null,
  role: "user",
  gender: "female",
  birth_date: "2020-02-03",
  presence: "away",
  last_seen_at: "2026-08-01T08:00:00Z",
  language: "zh-CN",
  created_at: "2026-07-31T00:00:00Z",
  elfie_count: 1,
  elfie_quota_override: null,
  effective_elfie_limit: 3,
  avatar_url: "/api/v1/admin/users/7/avatar",
} as const

describe("owner user API boundary", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("parses the exact canonical user view when listing users", async () => {
    // Given: the backend returns the final OwnerUserView.
    vi.mocked(requestJson).mockResolvedValue({ items: [member] })

    // When: the user list crosses the API boundary.
    const result = await ownerUsers()

    // Then: numeric identity and nullable display name are preserved.
    expect(result).toEqual([member])
  })

  it("rejects legacy identity and presence aliases", async () => {
    // Given: a stale backend returns only legacy aliases.
    vi.mocked(requestJson).mockResolvedValue({ items: [{
      id: "7",
      username: "member01",
      nickname: "Member",
      online_status: "online",
    }] })

    // When/Then: strict parsing rejects the payload.
    await expect(ownerUsers()).rejects.toMatchObject({ name: "ZodError" })
  })

  it("sends canonical create fields and parses the created user", async () => {
    // Given: the create endpoint returns a canonical user.
    vi.mocked(requestJson).mockResolvedValue(member)

    // When: an Owner creates a member.
    const result = await createManagedUser("member01", "Member", "secret", "user", "csrf")

    // Then: the request and response both use the final contract.
    expect(requestJson).toHaveBeenCalledWith("/api/v1/admin/users", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        account_id: "member01",
        display_name: "Member",
        password: "secret",
        role: "user",
      }),
    }))
    expect(result.user_id).toBe(7)
  })

  it("sends the selected Admin role without exposing a quota mutation", async () => {
    vi.mocked(requestJson).mockResolvedValue({ ...member, role: "admin" })

    await createManagedUser("admin01", "Admin", "secret", "admin", "csrf")

    expect(requestJson).toHaveBeenCalledWith("/api/v1/admin/users", expect.objectContaining({
      body: JSON.stringify({ account_id: "admin01", display_name: "Admin", password: "secret", role: "admin" }),
    }))
  })

  it("uses numeric IDs for quota, reset, and delete mutations", async () => {
    // Given: every mutation endpoint returns valid JSON.
    vi.mocked(ownerWrite)
      .mockResolvedValueOnce({ ...member, elfie_quota_override: 6, effective_elfie_limit: 6 })
      .mockResolvedValueOnce({})
    vi.mocked(requestJson).mockResolvedValue({ temporary_password: "fixture-value" })

    // When: all member mutations run.
    await updateManagedUser(7, { elfie_quota_override: 6 }, "csrf")
    await resetManagedUserPassword(7, "csrf")
    await deleteManagedUser(7, "csrf")

    // Then: each URL contains the numeric identity.
    expect(ownerWrite).toHaveBeenNthCalledWith(1, "/api/v1/admin/users/7", "PATCH", "csrf", {
      elfie_quota_override: 6,
    })
    expect(requestJson).toHaveBeenCalledWith("/api/v1/admin/users/7/reset-password", expect.objectContaining({ method: "POST" }))
    expect(ownerWrite).toHaveBeenNthCalledWith(2, "/api/v1/admin/users/7", "DELETE", "csrf")
  })

  it("validates temporary-password responses and accepts an empty delete response", async () => {
    // Given: reset contains malformed JSON while delete is intentionally empty.
    vi.mocked(requestJson).mockResolvedValue({ temporary_password: 123456 })
    vi.mocked(ownerWrite).mockResolvedValue({})

    // When/Then: both response boundaries fail loudly.
    await expect(resetManagedUserPassword(7, "csrf")).rejects.toMatchObject({ name: "ZodError" })
    await expect(deleteManagedUser(7, "csrf")).resolves.toBeUndefined()
  })
})
