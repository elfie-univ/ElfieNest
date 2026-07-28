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

const sharedModel = {
  model_id: "shared-model",
  display_name: "Shared Model",
  capabilities: ["text"],
  providers: [
    { provider_id: "openai", available: true, verification_status: "passed", benchmark_status: "passed", latency_ms: 120, latency_class: "fast", price_estimate: null },
    { provider_id: "anthropic", available: true, verification_status: "failed", benchmark_status: null, latency_ms: null, latency_class: null, price_estimate: null },
    { provider_id: "ollama", available: true, verification_status: "passed", benchmark_status: "passed", latency_ms: 32, latency_class: "fast", price_estimate: null },
  ],
} satisfies ModelMatrix["models"][number]

const openAiOnlyModel = {
  model_id: "openai-only",
  display_name: "OpenAI Only",
  capabilities: ["text"],
  providers: [
    { provider_id: "openai", available: true, verification_status: "passed", benchmark_status: null, latency_ms: null, latency_class: null, price_estimate: 0.2 },
    { provider_id: "anthropic", available: false, verification_status: "never", benchmark_status: null, latency_ms: null, latency_class: null, price_estimate: null },
    { provider_id: "ollama", available: false, verification_status: "never", benchmark_status: null, latency_ms: null, latency_class: null, price_estimate: null },
  ],
} satisfies ModelMatrix["models"][number]

const matrix = {
  providers: [
    { provider_id: "openai", name: "OpenAI", verification: { status: "passed", checked_at: "2026-07-26T00:00:00Z", latency_ms: 8, error: null } },
    { provider_id: "anthropic", name: "Anthropic", verification: { status: "failed", checked_at: "2026-07-26T00:00:00Z", latency_ms: null, error: "denied" } },
    { provider_id: "ollama", name: "Ollama", verification: { status: "passed", checked_at: "2026-07-26T00:00:00Z", latency_ms: 3, error: null } },
  ],
  models: [sharedModel, openAiOnlyModel],
} satisfies ModelMatrix

describe("ModelMatrixDialog", () => {
  beforeEach(() => {
    vi.mocked(ownerModelMatrix).mockResolvedValue(matrix)
    vi.mocked(benchmarkProviderModels).mockResolvedValue({ results: [] })
  })

  it("opens with current matrix data and refreshes the visible model list", async () => {
    const user = userEvent.setup()
    vi.mocked(ownerModelMatrix)
      .mockResolvedValueOnce(matrix)
      .mockResolvedValueOnce({
        ...matrix,
        models: [openAiOnlyModel],
      })

    render(<ModelMatrixDialog csrfToken="csrf" onOpenChange={vi.fn()} open />)

    expect(await screen.findByRole("rowheader", { name: "Shared Model" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "重新读取" }))

    expect(await screen.findByRole("rowheader", { name: "OpenAI Only" })).toBeInTheDocument()
    expect(screen.queryByRole("rowheader", { name: "Shared Model" })).not.toBeInTheDocument()
    expect(ownerModelMatrix).toHaveBeenCalledTimes(2)
  })

  it("renders a real model by provider matrix with unknown prices", async () => {
    render(<ModelMatrixDialog csrfToken="csrf" onOpenChange={vi.fn()} open />)

    const dialog = await screen.findByRole("dialog", { name: "支持模型与测速" })
    const table = within(dialog).getByRole("table", { name: "模型供应商矩阵" })
    expect(within(table).getByRole("columnheader", { name: "OpenAI" })).toBeInTheDocument()
    expect(within(table).getByRole("columnheader", { name: "Anthropic" })).toBeInTheDocument()
    expect(within(table).getByRole("columnheader", { name: "Ollama" })).toBeInTheDocument()
    expect(within(table).getByRole("rowheader", { name: "Shared Model" })).toBeInTheDocument()
    expect(within(table).getAllByText("未提供")).toHaveLength(3)
    expect(within(table).getByText("120ms")).toBeVisible()
  })

  it("uses the shared table primitive while keeping semantic rows, columns, and table-cell display", async () => {
    render(<ModelMatrixDialog csrfToken="csrf" onOpenChange={vi.fn()} open />)

    const table = await screen.findByRole("table", { name: "模型供应商矩阵" })
    expect(within(table).getAllByRole("columnheader")).toHaveLength(matrix.providers.length + 1)
    expect(within(table).getAllByRole("row")).toHaveLength(matrix.models.length + 1)
    expect(within(table).getAllByRole("rowheader")).toHaveLength(matrix.models.length)

    const availableCell = within(table).getByRole("cell", { name: /可用.*120ms/ })
    expect(availableCell).toBeInstanceOf(HTMLTableCellElement)
    if (!(availableCell instanceof HTMLTableCellElement)) return
    expect(getComputedStyle(availableCell).display).toBe("table-cell")
  })

  it("offers per-cell speed tests only for benchmarkable provider-model pairs", async () => {
    const user = userEvent.setup()
    render(<ModelMatrixDialog csrfToken="csrf" onOpenChange={vi.fn()} open />)

    await user.click(await screen.findByRole("button", { name: "测速 OpenAI Shared Model" }))

    expect(benchmarkProviderModels).toHaveBeenCalledWith(
      [{ provider_id: "openai", model_id: "shared-model" }],
      "csrf",
    )
    expect(screen.getByRole("button", { name: "测速 Anthropic Shared Model" })).toBeDisabled()
  })

  it("benchmarks only available cells from passed providers", async () => {
    const user = userEvent.setup()
    render(<ModelMatrixDialog csrfToken="csrf" onOpenChange={vi.fn()} open />)

    await user.click(await screen.findByRole("button", { name: "批量测速" }))

    expect(vi.mocked(benchmarkProviderModels)).toHaveBeenCalledWith(
      [
        { provider_id: "openai", model_id: "shared-model" },
        { provider_id: "ollama", model_id: "shared-model" },
        { provider_id: "openai", model_id: "openai-only" },
      ],
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
