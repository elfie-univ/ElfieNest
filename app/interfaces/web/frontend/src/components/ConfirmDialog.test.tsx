import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { i18n } from "i18next"
import { I18nextProvider } from "react-i18next"
import { useState } from "react"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "@/i18n/config"
import { initializeLocale, type SupportedLocale } from "@/i18n/locale"

import { ConfirmDialog } from "./ConfirmDialog"

function ConfirmFixture({ onConfirm, pending = false }: { readonly onConfirm: () => void; readonly pending?: boolean }) {
  const [open, setOpen] = useState(false)
  return <ConfirmDialog
    confirmLabel="确认删除"
    danger
    description="删除后无法恢复"
    onConfirm={onConfirm}
    onOpenChange={setOpen}
    open={open}
    pending={pending}
    title="删除供应商"
    trigger={<button type="button">删除</button>}
  />
}

function ExternalConfirmFixture() {
  const [open, setOpen] = useState(false)
  return <>
    <button onClick={() => setOpen(true)} type="button">外部删除</button>
    <ConfirmDialog description="外部确认" onConfirm={() => undefined} onOpenChange={setOpen} open={open} title="外部确认框" />
  </>
}

function renderWithLocale(children: React.ReactNode, locale: SupportedLocale): i18n {
  const instance = createI18n()
  initializeLocale(instance, {
    storage: localStorage,
    browserLanguages: [locale],
    documentElement: document.documentElement,
  })
  render(<I18nextProvider i18n={instance}>{children}</I18nextProvider>)
  return instance
}

function DefaultConfirmFixture({ pending = false }: { readonly pending?: boolean }) {
  const [open, setOpen] = useState(false)
  return <ConfirmDialog
    description="Shared confirmation copy"
    onConfirm={() => undefined}
    onOpenChange={setOpen}
    open={open}
    pending={pending}
    title="Shared dialog"
    trigger={<button type="button">Open shared dialog</button>}
  />
}

describe("ConfirmDialog", () => {
  it("cancels without confirming and restores trigger focus", async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    renderWithLocale(<ConfirmFixture onConfirm={onConfirm} />, "zh-CN")

    const trigger = screen.getByRole("button", { name: "删除" })
    await user.click(trigger)
    await user.click(screen.getByRole("button", { name: "取消" }))

    expect(onConfirm).not.toHaveBeenCalled()
    expect(trigger).toHaveFocus()
  })

  it("prevents repeated confirmation while pending", async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    renderWithLocale(<ConfirmFixture onConfirm={onConfirm} pending />, "zh-CN")

    await user.click(screen.getByRole("button", { name: "删除" }))

    expect(screen.getByRole("button", { name: "处理中…" })).toBeDisabled()
    await user.click(screen.getByRole("button", { name: "处理中…" }))
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it("restores focus when opened by an external control", async () => {
    const user = userEvent.setup()
    renderWithLocale(<ExternalConfirmFixture />, "zh-CN")

    const opener = screen.getByRole("button", { name: "外部删除" })
    await user.click(opener)
    await user.click(screen.getByRole("button", { name: "取消" }))

    expect(opener).toHaveFocus()
  })

  it("localizes default actions from the shared namespace", async () => {
    const user = userEvent.setup()
    renderWithLocale(<DefaultConfirmFixture />, "en-US")

    await user.click(screen.getByRole("button", { name: "Open shared dialog" }))

    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Confirm" })).toBeInTheDocument()
  })

  it("localizes the pending default action without changing custom copy", async () => {
    const user = userEvent.setup()
    renderWithLocale(<DefaultConfirmFixture pending />, "zh-CN")

    await user.click(screen.getByRole("button", { name: "Open shared dialog" }))

    expect(screen.getByRole("button", { name: "处理中…" })).toBeDisabled()
    expect(screen.getByText("Shared confirmation copy")).toBeInTheDocument()
  })
})
