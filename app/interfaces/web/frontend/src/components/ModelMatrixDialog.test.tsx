import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  benchmarkProviderModels,
  ownerModelMatrix,
  type ModelMatrix,
} from "../api/owner-providers"
import "../styles.css"
import { ModelMatrixDialog } from "./ModelMatrixDialog"

vi.mock("../api/owner-providers", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-providers")>()
  return {
    ...original,
    benchmarkProviderModels: vi.fn(),
    ownerModelMatrix: vi.fn(),
  }
})

const matrix = {
  connections: [
    { connection_id: "openai_api_0001", name: "OpenAI 工作", verification: { status: "passed", checked_at: "2026-07-26T00:00:00Z", latency_ms: 8, error: null } },
    { connection_id: "anthropic_api_0001", name: "Anthropic", verification: { status: "failed", checked_at: "2026-07-26T00:00:00Z", latency_ms: null, error: "denied" } },
    { connection_id: "ollama_0001", name: "Ollama", verification: { status: "passed", checked_at: "2026-07-26T00:00:00Z", latency_ms: 3, error: null } },
  ],
  models: [{
    model_key: "shared",
    display_name: "Shared Model",
    capabilities: ["text"],
    connections: [
      { connection_id: "openai_api_0001", model_id: "vendor-shared", available: true, verification_status: "passed", benchmark_status: "passed", latency_ms: 120, latency_class: "fast", price_estimate: null },
      { connection_id: "anthropic_api_0001", model_id: "shared-model", available: true, verification_status: "failed", benchmark_status: null, latency_ms: null, latency_class: null, price_estimate: null },
      { connection_id: "ollama_0001", model_id: "shared:latest", available: true, verification_status: "passed", benchmark_status: "passed", latency_ms: 32, latency_class: "fast", price_estimate: null },
    ],
  }, {
    model_key: "openai-only",
    display_name: "OpenAI Only",
    capabilities: ["text"],
    connections: [
      { connection_id: "openai_api_0001", model_id: "openai-only", available: true, verification_status: "passed", benchmark_status: null, latency_ms: null, latency_class: null, price_estimate: 0.2 },
      { connection_id: "anthropic_api_0001", model_id: null, available: false, verification_status: "never", benchmark_status: null, latency_ms: null, latency_class: null, price_estimate: null },
      { connection_id: "ollama_0001", model_id: null, available: false, verification_status: "never", benchmark_status: null, latency_ms: null, latency_class: null, price_estimate: null },
    ],
  }],
} satisfies ModelMatrix

describe("ModelMatrixDialog", () => {
  beforeEach(() => {
    vi.mocked(ownerModelMatrix).mockResolvedValue(matrix)
    vi.mocked(benchmarkProviderModels).mockResolvedValue({ results: [] })
  })

  it("renders models by connection instance", async () => {
    render(<ModelMatrixDialog csrfToken="csrf" onOpenChange={vi.fn()} open />)

    const table = await screen.findByRole("table", { name: "模型供应商矩阵" })
    expect(within(table).getByRole("columnheader", { name: "OpenAI 工作" })).toBeInTheDocument()
    expect(within(table).getByRole("columnheader", { name: "Anthropic" })).toBeInTheDocument()
    expect(within(table).getByRole("rowheader", { name: "Shared Model" })).toBeInTheDocument()
    expect(within(table).getByText("120ms")).toBeVisible()
  })

  it("refreshes visible model rows", async () => {
    const user = userEvent.setup()
    vi.mocked(ownerModelMatrix)
      .mockResolvedValueOnce(matrix)
      .mockResolvedValueOnce({ ...matrix, models: [matrix.models[1]!] })
    render(<ModelMatrixDialog csrfToken="csrf" onOpenChange={vi.fn()} open />)

    expect(await screen.findByRole("rowheader", { name: "Shared Model" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "重新读取" }))
    expect(await screen.findByRole("rowheader", { name: "OpenAI Only" })).toBeInTheDocument()
    expect(screen.queryByRole("rowheader", { name: "Shared Model" })).not.toBeInTheDocument()
  })

  it("benchmarks the endpoint model id from the selected connection cell", async () => {
    const user = userEvent.setup()
    render(<ModelMatrixDialog csrfToken="csrf" onOpenChange={vi.fn()} open />)

    await user.click(await screen.findByRole("button", { name: "测速 OpenAI 工作 Shared Model" }))

    expect(benchmarkProviderModels).toHaveBeenCalledWith(
      [{ connection_id: "openai_api_0001", model_id: "vendor-shared" }],
      "csrf",
    )
    expect(screen.getByRole("button", { name: "测速 Anthropic Shared Model" })).toBeDisabled()
  })

  it("batch benchmarks only available models on verified connections", async () => {
    const user = userEvent.setup()
    render(<ModelMatrixDialog csrfToken="csrf" onOpenChange={vi.fn()} open />)

    await user.click(await screen.findByRole("button", { name: "批量测速" }))

    expect(benchmarkProviderModels).toHaveBeenCalledWith([
      { connection_id: "openai_api_0001", model_id: "vendor-shared" },
      { connection_id: "ollama_0001", model_id: "shared:latest" },
      { connection_id: "openai_api_0001", model_id: "openai-only" },
    ], "csrf")
  })
})
