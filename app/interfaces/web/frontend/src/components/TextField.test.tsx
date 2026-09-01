import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { TextField } from "./TextField"

describe("TextField", () => {
  it("renders a true field row with one associated label and readable feedback", () => {
    render(
      <TextField
        error="请输入一个可以访问的 API Base URL，长中文错误必须完整保留。"
        hint="示例：https://host.example/v1"
        label="API Base URL"
        onChange={() => undefined}
        value=""
      />,
    )

    const field = screen.getByRole("group", { name: "API Base URL" })
    const input = within(field).getByRole("textbox", { name: "API Base URL" })

    expect(input).toHaveAttribute("aria-invalid", "true")
    expect(input).toHaveAccessibleDescription("请输入一个可以访问的 API Base URL，长中文错误必须完整保留。")
    expect(within(field).getAllByText("API Base URL")).toHaveLength(1)
  })

  it("masks non-login secrets without exposing them to password managers", () => {
    render(<TextField label="API Key" masked onChange={() => undefined} value="secret" />)

    const input = screen.getByRole("textbox", { name: "API Key" })
    expect(input).toHaveAttribute("type", "text")
    expect(input).toHaveAttribute("autocomplete", "off")
    expect(input).toHaveClass("input--masked")
  })
})
