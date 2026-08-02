import { beforeEach, describe, expect, it, vi } from "vitest"

import { ownerRooms } from "./owner-nest"
import { requestJson } from "./http"

vi.mock("./http", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("./http")>()
  return { ...original, requestJson: vi.fn() }
})

describe("owner Nest API boundary", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("normalizes semantic bed payloads into the floorplan contract", async () => {
    // Given: the backend emits numeric bed ids and the semantic label field.
    vi.mocked(requestJson).mockResolvedValue([{
      id: "local",
      name: "Local Nest",
      desired_bed_count: 4,
      applied_world_revision: 1,
      beds: [{
        id: 1,
        anchor_id: "bed-01",
        kind: "bed",
        label: "Bed 01",
        order: 0,
        active: true,
        occupant_id: null,
        occupant_name: null,
        occupant_owner_user_id: null,
        occupant_species_id: null,
        occupant_owner_account_id: null,
        occupant_owner_display_name: null,
      }],
      zones: [],
    }])

    // When: the real room payload crosses the API boundary.
    const [room] = await ownerRooms()

    // Then: the floorplan receives stable string ids and display names.
    expect(room?.beds).toEqual([{
      id: "1",
      anchor_id: "bed-01",
      name: "Bed 01",
      occupant_id: null,
      occupant_name: null,
      occupant_species_id: null,
    }])
  })
})
