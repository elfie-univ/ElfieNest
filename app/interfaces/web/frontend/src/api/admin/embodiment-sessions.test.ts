import { describe, expect, it, vi } from "vitest"

import { requestJson } from "../http"
import { embodimentSessions } from "./embodiment-sessions"

vi.mock("../http", () => ({ requestJson: vi.fn() }))

describe("administrator Embodiment sessions client", () => {
  it("reads only the existing read-only projection", async () => {
    vi.mocked(requestJson).mockResolvedValue({
      items: [{ elfie_id: "00000001", state: "hosted", body_id: "body-1" }],
    })

    expect(await embodimentSessions()).toEqual([
      { elfie_id: "00000001", state: "hosted", body_id: "body-1" },
    ])
    expect(requestJson).toHaveBeenCalledWith(
      "/api/v1/admin/runtime/embodiment-sessions",
    )
  })
})
