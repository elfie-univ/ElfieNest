import { afterEach, describe, expect, it, vi } from "vitest"

import { ApiError, ownerRead, requestJson } from "./http"

describe("requestJson", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("preserves FastAPI field validation details as typed API evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: [{
        type: "string_pattern_mismatch",
        loc: ["body", "provider_id"],
        msg: "String should match pattern",
      }],
    }), {
      status: 422,
      headers: { "Content-Type": "application/json" },
    })))

    await expect(requestJson("http://localhost/api/owner/providers/", { method: "POST" })).rejects.toEqual(
      new ApiError(422, "", [{
        type: "string_pattern_mismatch",
        loc: ["body", "provider_id"],
        msg: "String should match pattern",
      }]),
    )
  })

  it("reads the versioned error envelope used by authentication", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: {
        code: "authentication_failed",
        message: "登录账号或密码错误",
      },
    }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    })))

    await expect(requestJson("http://localhost/api/v1/auth/login", { method: "POST" })).rejects.toEqual(
      new ApiError(401, "登录账号或密码错误", [], "authentication_failed"),
    )
  })

  it("bypasses the browser cache when reloading owner state", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }))
    vi.stubGlobal("fetch", fetchMock)

    await ownerRead("http://localhost/api/v1/admin/model-providers/connections")

    const request = fetchMock.mock.calls[0]?.[0]
    expect(request).toBeInstanceOf(Request)
    expect((request as Request).cache).toBe("no-store")
  })
})
