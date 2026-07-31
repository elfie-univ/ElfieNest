import { afterEach, describe, expect, it, vi } from "vitest"

import { ApiError, requestJson } from "./http"

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
})
