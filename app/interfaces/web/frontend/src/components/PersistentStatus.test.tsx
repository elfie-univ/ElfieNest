import { act, fireEvent, render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "../i18n/config"
import { PersistentStatus } from "./PersistentStatus"

describe("PersistentStatus", () => {
  it("stays visible after timers and exposes its retry action", () => {
    vi.useFakeTimers()
    const onRetry = vi.fn()
    render(<I18nextProvider i18n={createI18n()}><PersistentStatus
      detail="The runtime did not answer."
      kind="error"
      message="Runtime unavailable."
      retry={{ label: "Retry", onSelect: onRetry }}
    /></I18nextProvider>)

    expect(screen.getByRole("alert")).toHaveTextContent("Runtime unavailable.")
    act(() => { vi.advanceTimersByTime(60000) })
    expect(screen.getByRole("alert")).toHaveTextContent("Runtime unavailable.")
    fireEvent.click(screen.getByRole("button", { name: "Retry" }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
