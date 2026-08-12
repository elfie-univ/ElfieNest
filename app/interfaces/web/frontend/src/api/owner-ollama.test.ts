import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  ownerOllamaStatus,
  pullOllamaModels,
  startOllama,
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
  models: [{
    id: "qwen2.5:0.5b",
    display_name: "qwen2.5:0.5b",
    installed: true,
    recommended: true,
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
})
