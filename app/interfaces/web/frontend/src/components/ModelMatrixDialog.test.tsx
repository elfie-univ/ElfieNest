import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  benchmarkProviderModels,
  ownerModelMatrix,
  validateAllProviderModels,
  type ModelMatrix,
} from "../api/owner-providers"
import { createI18n } from "../i18n/config"
import { ModelMatrixDialog } from "./ModelMatrixDialog"

vi.mock("../api/owner-providers", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/owner-providers")>()
  return {
    ...original,
    benchmarkProviderModels: vi.fn(),
    ownerModelMatrix: vi.fn(),
    validateAllProviderModels: vi.fn(),
  }
})

const matrix = {
  snapshot: { mode: "latest", run_id: "run-1", status: "passed" },
  connections: [{
    connection_id: "conn-openai",
    name: "OpenAI Main",
    verification: { status: "passed", checked_at: "2026-07-30T00:00:00Z", latency_ms: 45, error: null },
  }],
  models: [{
    model_key: "gpt-test",
    display_name: "GPT Test",
    capabilities: ["text"],
    connections: [{
      connection_id: "conn-openai",
      model_id: "gpt-test",
      available: true,
      verification_status: "passed",
      benchmark_status: "passed",
      latency_ms: 45,
      latency_class: "fast",
      price_estimate: null,
    }],
  }],
} satisfies ModelMatrix

describe("ModelMatrixDialog v2 behavior", () => {
  beforeEach(() => {
    vi.mocked(ownerModelMatrix).mockResolvedValue(matrix)
    vi.mocked(benchmarkProviderModels).mockResolvedValue({
      run_id: "bench-2",
      status: "passed",
      results: [{
        connection_id: "conn-openai",
        model_id: "gpt-test",
        status: "passed",
        checked_at: "2026-07-30T00:00:01Z",
        latency_ms: 40,
        latency_class: "fast",
        error: null,
      }],
    })
    vi.mocked(validateAllProviderModels).mockResolvedValue({
      run_id: "validate-2",
      status: "passed",
      results: [{ subject: "conn-openai/gpt-test", status: "passed" }],
    })
  })

  it("renders the connection-model matrix from current report evidence", async () => {
    renderDialog()

    const dialog = screen.getByRole("dialog", { name: "同模型对比" })
    expect(await within(dialog).findByRole("columnheader", { name: "OpenAI Main" })).toBeInTheDocument()
    expect(within(dialog).getByRole("row", { name: /GPT Test.*可用.*45ms/ })).toBeInTheDocument()
  })

  it("benchmarks the visible verified combinations and refreshes the matrix", async () => {
    const user = userEvent.setup()
    renderDialog()

    await user.click(await screen.findByRole("button", { name: "批量对比" }))
    expect(benchmarkProviderModels).toHaveBeenCalledWith(
      [{ connection_id: "conn-openai", model_id: "gpt-test" }],
      "csrf",
    )
    expect(await screen.findByText("对比完成：1 个成功，0 个失败。")).toBeInTheDocument()
    expect(vi.mocked(ownerModelMatrix).mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it("switches visible copy without losing the loaded report", async () => {
    const instance = renderDialog()
    expect(await screen.findByText("GPT Test")).toBeInTheDocument()

    await instance.changeLanguage("en-US")
    expect(screen.getByRole("dialog", { name: "Same-model comparison" })).toBeInTheDocument()
    expect(screen.getByText("GPT Test")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Compare all" })).toBeInTheDocument()
  })
})

function renderDialog(): ReturnType<typeof createI18n> {
  const instance = createI18n()
  document.documentElement.lang = "zh-CN"
  render(
    <I18nextProvider i18n={instance}>
      <ModelMatrixDialog csrfToken="csrf" onOpenChange={vi.fn()} open />
    </I18nextProvider>,
  )
  return instance
}
