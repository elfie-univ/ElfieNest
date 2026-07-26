import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { describe, expect, it, vi } from "vitest"

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

describe("ConfirmDialog", () => {
  it("cancels without confirming and restores trigger focus", async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(<ConfirmFixture onConfirm={onConfirm} />)

    const trigger = screen.getByRole("button", { name: "删除" })
    await user.click(trigger)
    await user.click(screen.getByRole("button", { name: "取消" }))

    expect(onConfirm).not.toHaveBeenCalled()
    expect(trigger).toHaveFocus()
  })

  it("prevents repeated confirmation while pending", async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(<ConfirmFixture onConfirm={onConfirm} pending />)

    await user.click(screen.getByRole("button", { name: "删除" }))

    expect(screen.getByRole("button", { name: "处理中…" })).toBeDisabled()
    await user.click(screen.getByRole("button", { name: "处理中…" }))
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it("restores focus when opened by an external control", async () => {
    const user = userEvent.setup()
    render(<ExternalConfirmFixture />)

    const opener = screen.getByRole("button", { name: "外部删除" })
    await user.click(opener)
    await user.click(screen.getByRole("button", { name: "取消" }))

    expect(opener).toHaveFocus()
  })
})
