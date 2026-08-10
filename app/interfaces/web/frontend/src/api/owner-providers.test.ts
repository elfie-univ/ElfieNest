import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  changeProviderConnectionLifecycle,
  ownerModelMatrix,
  ownerProviderCatalog,
} from "./owner-providers"
import { ownerRead, ownerWrite } from "./http"

vi.mock("./http", () => ({ ownerRead: vi.fn(), ownerWrite: vi.fn() }))

const verification = {
  status: "never" as const,
  checked_at: null,
  latency_ms: null,
  error: null,
  validation_mode: "none" as const,
  cache_hit: false,
  needs_full_validation: false,
  needs_heartbeat: false,
  full_run_id: null,
  full_checked_at: null,
  heartbeat_checked_at: null,
  heartbeat_status: null,
  representative_model_id: null,
  reason: null,
}

describe("versioned model Provider client", () => {
  beforeEach(() => vi.clearAllMocks())

  it("reads the named catalog envelope", async () => {
    vi.mocked(ownerRead).mockResolvedValue({ items: [{
      catalog_id: "openai_api",
      name: "OpenAI",
      brand: { brand_id: "openai", name: "OpenAI", logo_asset: "/brands/openai.svg" },
      connection_method: "api_key",
      oauth_available: false,
      usage_scope: "general",
      discovery_strategy: "standard_models",
      api_mode: "chat_completions",
    }] })

    const result = await ownerProviderCatalog()

    expect(result[0]?.catalog_id).toBe("openai_api")
    expect(ownerRead).toHaveBeenCalledWith("/api/v1/admin/model-providers/catalog")
  })

  it("writes lifecycle actions only through the versioned resource", async () => {
    vi.mocked(ownerWrite).mockResolvedValue({
      connection_id: "openai_api_0001",
      catalog_id: "openai_api",
      alias: "Primary",
      api_base: "https://api.openai.com/v1",
      api_mode: "chat_completions",
      auth_type: "bearer",
      has_api_key: true,
      enabled: false,
      archived: false,
      usage_scope: "general",
      verification,
      models: [],
      model_refresh: null,
    })

    await changeProviderConnectionLifecycle("openai_api_0001", "disable", "csrf")

    expect(ownerWrite).toHaveBeenCalledWith(
      "/api/v1/admin/model-providers/connections/openai_api_0001/disable",
      "POST",
      "csrf",
    )
  })

  it("accepts an empty current matrix snapshot", async () => {
    vi.mocked(ownerRead).mockResolvedValue({
      snapshot: {
        mode: "current",
        run_id: null,
        as_of: null,
        status: null,
        started_at: null,
        finished_at: null,
      },
      connections: [],
      models: [],
    })

    const result = await ownerModelMatrix()

    expect(result.snapshot.mode).toBe("current")
    expect(ownerRead).toHaveBeenCalledWith(
      "/api/v1/admin/model-providers/model-matrix",
    )
  })
})
