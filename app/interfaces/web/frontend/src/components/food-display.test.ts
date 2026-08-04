import { describe, expect, it } from "vitest"

import type { FoodPackage } from "../api/owner-foods"
import { formatLatency, projectFoodDisplay } from "./food-display"

const food = {
  key: "custom",
  display_name: "工作粮",
  system_role: null,
  enabled: true,
  archived: false,
  visibility_mode: "users",
  visible_user_ids: [2, 3],
  roles: {
    primary: { model: "cloud/main" },
    reasoning: { model: "cloud/unknown" },
    vision: null,
    tool: null,
    fallback: { model: "local/qwen" },
  },
  health: "healthy",
  locality: "mixed",
  latest_evidence_at: null,
} satisfies FoodPackage

const connections = [
  {
    connection_id: "cloud",
    alias: "云端",
    models: [
      {
        id: "main",
        display_name: "主模型",
        available: true,
        hidden: false,
        retired: false,
        verification: { status: "passed", checked_at: null, latency_ms: 1250, error: null },
      },
    ],
  },
  {
    connection_id: "local",
    alias: "本地",
    models: [
      {
        id: "qwen",
        display_name: "Qwen 0.5B",
        available: false,
        hidden: false,
        retired: false,
        verification: { status: "never", checked_at: null, latency_ms: null, error: null },
      },
    ],
  },
] as const

describe("food display projection", () => {
  it("uses connection aliases and model display names while preserving per-model state", () => {
    const projection = projectFoodDisplay(food, connections, 3)

    expect(projection.models.primary.label).toBe("云端 / 主模型")
    expect(projection.models.primary.status).toBe("available")
    expect(projection.models.primary.latencyLabel).toBe("1.3 s")
    expect(projection.models.reasoning.label).toBe("cloud/unknown")
    expect(projection.models.reasoning.status).toBe("unverified")
    expect(projection.models.fallback.status).toBe("unavailable")
    expect(projection.visibility).toEqual({ kind: "users", count: 2, allCurrentUsers: false })
  })

  it("marks system food as globally visible and missing visibility as a read failure", () => {
    expect(projectFoodDisplay({ ...food, system_role: "common" }, connections).visibility).toEqual({ kind: "all", count: null })
    expect(projectFoodDisplay({ ...food, visibility_mode: "global", visible_user_ids: [] }, connections).visibility).toEqual({ kind: "all", count: null })
  })

  it("does not invent a latency value", () => {
    expect(formatLatency(null)).toBeNull()
    expect(formatLatency(999)).toBe("999 ms")
    expect(formatLatency(1000)).toBe("1.0 s")
  })
})
