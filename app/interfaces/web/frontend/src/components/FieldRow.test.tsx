import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { FieldRow } from "./FieldRow"

describe("FieldRow", () => {
  it("associates one visible label with one control and keeps feedback in the control column", () => {
    render(
      <FieldRow
        control={<input id="runtime-tick" />}
        error="必须在 0.1 到 3600 秒之间，并且这段中文错误不能被截断。"
        hint="用于控制 Nest 主循环频率。"
        inputId="runtime-tick"
        label="运行 Tick（秒）"
      />,
    )

    const field = screen.getByRole("group", { name: "运行 Tick（秒）" })
    const control = within(field).getByRole("textbox", { name: "运行 Tick（秒）" })
    const label = within(field).getByText("运行 Tick（秒）")

    expect(control).toHaveAccessibleDescription("必须在 0.1 到 3600 秒之间，并且这段中文错误不能被截断。")
    expect(control).toHaveAttribute("aria-invalid", "true")
    expect(label).toHaveAttribute("for", "runtime-tick")
    expect(within(field).getAllByText("运行 Tick（秒）")).toHaveLength(1)
    expect(within(field).getByText("用于控制 Nest 主循环频率。")).toBeInTheDocument()
  })
})
