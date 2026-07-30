import { describe, expect, it } from "vitest"

import type { ModelMatrix } from "../api/owner-providers"

describe("model matrix contract", () => {
  it("carries report snapshot identity", () => {
    const matrix: ModelMatrix = {
      snapshot: { mode: "run", run_id: "run_1", status: "complete" },
      connections: [],
      models: [],
    }
    expect(matrix.snapshot.run_id).toBe("run_1")
  })
})
