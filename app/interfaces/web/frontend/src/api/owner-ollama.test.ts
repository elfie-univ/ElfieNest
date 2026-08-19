import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  ownerOllamaStatus,
  pullOllamaModels,
  startOllama,
  supportedOllamaModelCounts,
  verifyOllamaModels,
} from "./owner-ollama"
import { ownerRead, ownerWrite } from "./http"

vi.mock("./http", () => ({ ownerRead: vi.fn(), ownerWrite: vi.fn() }))

const status = {
  state: "healthy" as const,
  endpoint: "http://127.0.0.1:11434",
  version: "0.12.0",
  memory_gb: 8,
  recommended_model: "qwen2.5:0.5b",
  installed_model_count: 1,
  model_counts: { installed: 1, available: 1, degraded: 0, pending: 0, unavailable: 0 },
  models: [{
    id: "qwen2.5:0.5b",
    display_name: "qwen2.5:0.5b",
    installed: true,
    recommended: true,
    available: true,
    availability_status: "available" as const,
  }],
  task: null,
}

describe("versioned Ollama Provider client", () => {
  beforeEach(() => vi.clearAllMocks())

  it("reads local status from the model Provider resource", async () => {
    vi.mocked(ownerRead).mockResolvedValue(status)

    await expect(ownerOllamaStatus()).resolves.toEqual(status)
    expect(ownerRead).toHaveBeenCalledWith(
      "/api/v1/admin/model-providers/ollama",
    )
  })

  it("writes start and model pulls only through versioned resources", async () => {
    vi.mocked(ownerWrite).mockResolvedValue(status)

    await startOllama("csrf")
    await pullOllamaModels(["qwen2.5:0.5b"], "csrf")

    expect(ownerWrite).toHaveBeenNthCalledWith(
      1,
      "/api/v1/admin/model-providers/ollama/start",
      "POST",
      "csrf",
    )
    expect(ownerWrite).toHaveBeenNthCalledWith(
      2,
      "/api/v1/admin/model-providers/ollama/models/pull",
      "POST",
      "csrf",
      { model_ids: ["qwen2.5:0.5b"], confirmed: true },
    )
  })

  it("validates only through the local Provider resource", async () => {
    vi.mocked(ownerWrite).mockResolvedValue(status)

    await verifyOllamaModels("csrf")

    expect(ownerWrite).toHaveBeenCalledWith(
      "/api/v1/admin/model-providers/ollama/verify",
      "POST",
      "csrf",
      undefined,
      { timeout: false },
    )
  })

  it("counts only installed models from the supported product list", () => {
    const counts = supportedOllamaModelCounts({
      models: [
        ...status.models,
        { id: "qwen3.5:0.8b", display_name: "qwen3.5:0.8b", installed: true, recommended: false, available: true, availability_status: "degraded" },
        { id: "custom:latest", display_name: "custom:latest", installed: true, recommended: false, available: false, availability_status: "unknown" },
      ],
    }, ["qwen2.5:0.5b", "qwen3.5:0.8b"])

    expect(counts).toEqual({ installed: 2, available: 1, degraded: 1, pending: 0, unavailable: 0 })
  })
})
