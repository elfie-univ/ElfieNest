import { describe, expect, it } from "vitest"

import type { ProviderConnection, ProviderModel } from "../api/owner-providers"

describe("Provider connection contract", () => {
  it("uses contract lifecycle and discovery source fields", () => {
    const model: ProviderModel = {
      id: "gpt",
      display_name: "GPT",
      canonical_model_id: null,
      source: "official",
      context_window_tokens: null,
      max_output_tokens: null,
      supports_tools: true,
      supports_vision: false,
      supports_reasoning: false,
      hidden: false,
      retired: false,
      available: true,
    }
    const connection = {
      archived: false,
      enabled: true,
      models: [model],
    } as ProviderConnection
    expect(connection.models[0]?.source).toBe("official")
    expect(connection.archived).toBe(false)
  })
})
