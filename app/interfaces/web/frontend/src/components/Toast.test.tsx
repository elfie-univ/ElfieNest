import { act, fireEvent, render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, describe, expect, it, vi } from "vitest"

import { createI18n } from "../i18n/config"
import { ToastProvider, useToast } from "./ui/toast"

function ToastFixture({ onAction }: { readonly onAction?: () => void }) {
  const { show } = useToast()
  return <div>
    <button onClick={() => show({ kind: "success", message: "Saved." })} type="button">show-success</button>
    <button onClick={() => show({ kind: "info", message: "Info." })} type="button">show-info</button>
    <button onClick={() => show({ action: { label: "Retry", onSelect: onAction ?? (() => undefined) }, kind: "warning", message: "Warning." })} type="button">show-warning</button>
    <button onClick={() => show({ kind: "error", message: "Error." })} type="button">show-error</button>
    <button onClick={() => show({ kind: "info", message: "Closable." })} type="button">show-closable</button>
    <button onClick={() => {
      show({ dedupeKey: "one", kind: "info", message: "First." })
      show({ dedupeKey: "two", kind: "info", message: "Second." })
      show({ dedupeKey: "three", kind: "info", message: "Third." })
      show({ dedupeKey: "four", kind: "info", message: "Fourth." })
      show({ dedupeKey: "two", kind: "info", message: "Second updated." })
    }} type="button">show-many</button>
  </div>
}

function renderToastFixture(onAction?: () => void) {
  return render(<I18nextProvider i18n={createI18n()}><ToastProvider><ToastFixture {...(onAction ? { onAction } : {})} /></ToastProvider></I18nextProvider>)
}

describe("ToastProvider", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it("auto-dismisses a success toast at the shared duration", () => {
    vi.useFakeTimers()
    renderToastFixture()
    fireEvent.click(screen.getByRole("button", { name: "show-success" }))

    expect(screen.getByText("Saved.")).toBeInTheDocument()
    act(() => { vi.advanceTimersByTime(3999) })
    expect(screen.getByText("Saved.")).toBeInTheDocument()
    act(() => { vi.advanceTimersByTime(1) })
    expect(screen.queryByText("Saved.")).not.toBeInTheDocument()
  })

  it.each([
    ["info", "show-info", "Info.", 5000],
    ["warning", "show-warning", "Warning.", 8000],
    ["error", "show-error", "Error.", 10000],
  ] as const)("uses the %s default duration and semantic kind", (kind, trigger, message, duration) => {
    vi.useFakeTimers()
    renderToastFixture()
    fireEvent.click(screen.getByRole("button", { name: trigger }))

    expect(screen.getByText(message).closest("[data-kind]")).toHaveAttribute("data-kind", kind)
    act(() => { vi.advanceTimersByTime(duration - 1) })
    expect(screen.getByText(message)).toBeInTheDocument()
    act(() => { vi.advanceTimersByTime(1) })
    expect(screen.queryByText(message)).not.toBeInTheDocument()
  })

  it("runs an action and dismisses the toast", () => {
    const onAction = vi.fn()
    renderToastFixture(onAction)
    fireEvent.click(screen.getByRole("button", { name: "show-warning" }))
    fireEvent.click(screen.getByRole("button", { name: "Retry" }))

    expect(onAction).toHaveBeenCalledOnce()
    expect(screen.queryByText("Warning.")).not.toBeInTheDocument()
  })

  it("supports localized close, keyboard dismissal, dedupe, and a three-toast cap", () => {
    renderToastFixture()
    fireEvent.click(screen.getByRole("button", { name: "show-closable" }))
    expect(screen.getByRole("button", { name: "关闭" })).toBeInTheDocument()
    fireEvent.keyDown(document, { key: "Escape" })
    expect(screen.queryByText("Closable.")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "show-many" }))
    expect(screen.queryByText("First.")).not.toBeInTheDocument()
    expect(screen.getByText("Second updated.")).toBeInTheDocument()
    expect(screen.getByText("Third.")).toBeInTheDocument()
    expect(screen.getByText("Fourth.")).toBeInTheDocument()
  })
})
