import { afterEach, describe, expect, it, vi } from "vitest"

import { ApiError, requestJson } from "./http"

describe("requestJson", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("turns FastAPI field validation details into a readable API error", async () => {
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
      new ApiError(422, "供应商 ID：格式不正确"),
    )
  })
})
