import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it } from "vitest"

import { createI18n } from "../i18n/config"
import { ManageDialog } from "./ManageDialog"

function DialogFixture() {
  const [open, setOpen] = useState(false)
  return <ManageDialog
    description="填写连接信息"
    onOpenChange={setOpen}
    open={open}
    title="编辑连接"
    trigger={<button type="button">打开编辑</button>}
  >
    <label htmlFor="dialog-name">名称</label>
    <input id="dialog-name" />
  </ManageDialog>
}

function ExternalTriggerFixture() {
  const [open, setOpen] = useState(false)
  return <>
    <button onClick={() => setOpen(true)} type="button">外部打开</button>
    <ManageDialog onOpenChange={setOpen} open={open} title="外部弹窗">
      <button type="button">弹窗操作</button>
    </ManageDialog>
  </>
}

describe("ManageDialog", () => {
  it("moves focus into the dialog and restores it after Escape", async () => {
    const user = userEvent.setup()
    render(<I18nextProvider i18n={createI18n()}><DialogFixture /></I18nextProvider>)

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
    render(<I18nextProvider i18n={createI18n()}><ExternalTriggerFixture /></I18nextProvider>)

    const opener = screen.getByRole("button", { name: "外部打开" })
    await user.click(opener)
    await user.keyboard("{Escape}")

    expect(opener).toHaveFocus()
  })
})
