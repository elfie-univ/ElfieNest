import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  ownerRuntimeTools,
  updateOwnerTool,
  verifyOwnerTool,
} from "./owner-tools"
import { ownerRead, ownerWrite } from "./http"

vi.mock("./http", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("./http")>()
  return {
    ...original,
    ownerRead: vi.fn(),
    ownerWrite: vi.fn(),
  }
})

const webSearch = {
  enabled: true,
  provider: "duckduckgo",
  api_base: "",
  max_results: 3,
  max_result_bytes: 16000,
  timeout_seconds: 5,
  max_tool_calls: 3,
  max_total_result_bytes: 48000,
  has_api_key: false,
} as const

const localFile = {
  enabled: false,
  root: "",
  root_policy: "elfie_workspace",
  max_read_bytes: 65536,
  max_items: 200,
  max_result_bytes: 16000,
  max_tool_calls: 3,
  max_total_result_bytes: 48000,
  has_api_key: false,
} as const

describe("owner tools API boundary", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("parses the two safe tools and strips a secret accidentally returned by a stale server", async () => {
    // Given: the server returns the public tool projection plus a legacy secret field.
    vi.mocked(ownerRead).mockResolvedValue({
      tools: {
        web_search: { ...webSearch, api_key: "must-not-cross-the-boundary" },
        local_file: localFile,
      },
    })

    // When: the owner reads the tool configuration.
    const result = await ownerRuntimeTools()

    // Then: only the public, typed projection reaches the UI.
    expect(result.web_search).toEqual(webSearch)
    expect(result.local_file).toEqual(localFile)
    expect("api_key" in result.web_search).toBe(false)
    expect(ownerRead).toHaveBeenCalledWith("/api/owner/runtime/tools/")
  })

  it("sends only the explicit web search fields and parses the saved config", async () => {
    // Given: the update endpoint returns the public saved configuration.
    vi.mocked(ownerWrite).mockResolvedValue({ tool_key: "web_search", config: webSearch })

    // When: the owner saves web search settings without changing its secret.
    const result = await updateOwnerTool("web_search", {
      enabled: false,
      provider: "brave",
      api_base: "https://search.example.test",
      max_results: 5,
      max_result_bytes: 24000,
    }, "csrf-token")

    // Then: only the route's supported fields are sent.
    expect(ownerWrite).toHaveBeenCalledWith(
      "/api/owner/runtime/tools/web_search",
      "PUT",
      "csrf-token",
      {
        enabled: false,
        provider: "brave",
        api_base: "https://search.example.test",
        max_results: 5,
        max_result_bytes: 24000,
      },
    )
    expect(result).toEqual(webSearch)
  })

  it("keeps local file updates to enabled and read size only", async () => {
    // Given: the local file update endpoint returns its public config.
    vi.mocked(ownerWrite).mockResolvedValue({ tool_key: "local_file", config: localFile })

    // When: the owner changes the read-only tool's limit.
    await updateOwnerTool("local_file", { enabled: true, max_read_bytes: 32768 }, "csrf-token")

    // Then: no root, write, delete, or execution field can cross the boundary.
    expect(ownerWrite).toHaveBeenCalledWith(
      "/api/owner/runtime/tools/local_file",
      "PUT",
      "csrf-token",
      { enabled: true, max_read_bytes: 32768 },
    )
  })

  it("parses a validation suite from the existing verify endpoint", async () => {
    // Given: the validation endpoint returns the existing ValidationSuite shape.
    vi.mocked(ownerWrite).mockResolvedValue({
      name: "tool:local_file",
      passed: true,
      summary: { passed: 1, failed: 0, warning: 0, skipped: 0 },
      results: [{
        check_id: "tool.local_file",
        status: "passed",
        message: "Read-only local file validation passed",
        duration_ms: 2.5,
        provider: null,
        model: null,
        details: {},
      }],
    })

    // When: the owner verifies the local file tool.
    const result = await verifyOwnerTool("local_file", "csrf-token")

    // Then: the result remains typed and the existing endpoint is used.
    expect(result.passed).toBe(true)
    expect(ownerWrite).toHaveBeenCalledWith(
      "/api/owner/runtime/tools/local_file/verify",
      "POST",
      "csrf-token",
    )
  })

})
