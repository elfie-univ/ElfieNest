import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { describe, expect, it } from "vitest"

import { ManagerDialog } from "./ManagerDialog"

function DialogFixture() {
  const [open, setOpen] = useState(false)
  return <ManagerDialog
    description="填写连接信息"
    onOpenChange={setOpen}
    open={open}
    title="编辑连接"
    trigger={<button type="button">打开编辑</button>}
  >
    <label htmlFor="dialog-name">名称</label>
    <input id="dialog-name" />
  </ManagerDialog>
}

function ExternalTriggerFixture() {
  const [open, setOpen] = useState(false)
  return <>
    <button onClick={() => setOpen(true)} type="button">外部打开</button>
    <ManagerDialog onOpenChange={setOpen} open={open} title="外部弹窗">
      <button type="button">弹窗操作</button>
    </ManagerDialog>
  </>
}

describe("ManagerDialog", () => {
  it("moves focus into the dialog and restores it after Escape", async () => {
    const user = userEvent.setup()
    render(<DialogFixture />)

    const trigger = screen.getByRole("button", { name: "打开编辑" })
    await user.click(trigger)

    expect(screen.getByRole("dialog", { name: "编辑连接" })).toBeVisible()
    expect(screen.getByRole("textbox", { name: "名称" })).toHaveFocus()

    await user.keyboard("{Escape}")

    expect(screen.queryByRole("dialog", { name: "编辑连接" })).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it("restores focus when the opener lives outside the dialog primitive", async () => {
    const user = userEvent.setup()
    render(<ExternalTriggerFixture />)

    const opener = screen.getByRole("button", { name: "外部打开" })
    await user.click(opener)
    await user.keyboard("{Escape}")

    expect(opener).toHaveFocus()
  })
})
