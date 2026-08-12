import { beforeEach, describe, expect, it, vi } from "vitest"

import { requestJson } from "../http"
import { mobileAccess, MobileAccessSchema } from "./runtime"

vi.mock("../http", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../http")>()
  return { ...original, requestJson: vi.fn() }
})

describe("administrator Runtime API boundary", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("reads mobile access from the sole versioned Runtime resource", async () => {
    vi.mocked(requestJson).mockResolvedValue({
      available: true,
      urls: ["http://192.168.1.8:8000/"],
    })

    await expect(mobileAccess()).resolves.toEqual({
      available: true,
      urls: ["http://192.168.1.8:8000/"],
    })
    expect(requestJson).toHaveBeenCalledWith(
      "/api/v1/admin/runtime/mobile-access",
    )
  })

  it("rejects loose mobile access projections", () => {
    expect(
      MobileAccessSchema.safeParse({
        available: true,
        urls: ["http://192.168.1.8:8000/"],
        ws_port: 8766,
      }).success,
    ).toBe(false)
  })
})
