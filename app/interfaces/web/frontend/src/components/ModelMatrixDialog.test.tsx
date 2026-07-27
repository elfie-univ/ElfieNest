import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  benchmarkProviderModels,
  ownerModelMatrix,
  type ModelMatrix,
} from "../api/owner-providers"
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
  providers: [
    { provider_id: "openai", name: "OpenAI", verification: { status: "passed", checked_at: "2026-07-26T00:00:00Z", latency_ms: 8, error: null } },
    { provider_id: "anthropic", name: "Anthropic", verification: { status: "failed", checked_at: "2026-07-26T00:00:00Z", latency_ms: null, error: "denied" } },
  ],
  models: [{
    model_id: "shared-model",
    display_name: "Shared Model",
    capabilities: ["text"],
    providers: [
      { provider_id: "openai", available: true, verification_status: "passed", benchmark_status: "passed", latency_ms: 120, latency_class: "fast", price_estimate: null },
      { provider_id: "anthropic", available: true, verification_status: "failed", benchmark_status: null, latency_ms: null, latency_class: null, price_estimate: null },
    ],
  }],
} satisfies ModelMatrix

describe("ModelMatrixDialog", () => {
  beforeEach(() => {
    vi.mocked(ownerModelMatrix).mockResolvedValue(matrix)
    vi.mocked(benchmarkProviderModels).mockResolvedValue({ results: [] })
  })

  it("renders a real model by provider matrix with unknown prices", async () => {
    render(<ModelMatrixDialog csrfToken="csrf" onOpenChange={vi.fn()} open />)

    const dialog = await screen.findByRole("dialog", { name: "支持模型与测速" })
    const table = within(dialog).getByRole("table", { name: "模型供应商矩阵" })
    expect(within(table).getByRole("columnheader", { name: "OpenAI" })).toBeInTheDocument()
    expect(within(table).getByRole("columnheader", { name: "Anthropic" })).toBeInTheDocument()
    expect(within(table).getByRole("rowheader", { name: "Shared Model" })).toBeInTheDocument()
    expect(within(table).getAllByText("未提供")).toHaveLength(2)
    expect(within(table).getByText("120ms")).toHaveClass("latency--fast")
  })

  it("benchmarks only available cells from passed providers", async () => {
    const user = userEvent.setup()
    render(<ModelMatrixDialog csrfToken="csrf" onOpenChange={vi.fn()} open />)

    await user.click(await screen.findByRole("button", { name: "批量测速" }))

    expect(vi.mocked(benchmarkProviderModels)).toHaveBeenCalledWith(
      [{ provider_id: "openai", model_id: "shared-model" }],
      "csrf",
    )
  })

  it("disables benchmarking when no verified provider-model pair exists", async () => {
    vi.mocked(ownerModelMatrix).mockResolvedValue({
      ...matrix,
      providers: matrix.providers.map((provider) => ({
        ...provider,
        verification: { ...provider.verification, status: "failed" as const },
      })),
    })

    render(<ModelMatrixDialog csrfToken="csrf" onOpenChange={vi.fn()} open />)

    expect(await screen.findByRole("button", { name: "批量测速" })).toBeDisabled()
  })
})
