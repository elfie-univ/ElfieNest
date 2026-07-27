import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { describe, expect, it } from "vitest"

import { NumberField } from "./NumberField"

function NumberFixture() {
  const [value, setValue] = useState(4)
  return <NumberField label="床位数" max={5} min={1} onChange={setValue} value={value} />
}

describe("NumberField", () => {
  it("steps within bounds and normalizes malformed input on blur", async () => {
    const user = userEvent.setup()
    render(<NumberFixture />)

    const field = screen.getByRole("textbox", { name: "床位数" })
    await user.click(screen.getByRole("button", { name: "增加床位数" }))
    expect(field).toHaveValue("5")
    await user.click(screen.getByRole("button", { name: "增加床位数" }))
    expect(field).toHaveValue("5")

    await user.clear(field)
    await user.type(field, "not-a-number")
    await user.tab()
    expect(field).toHaveValue("5")

    await user.click(screen.getByRole("button", { name: "减少床位数" }))
    expect(field).toHaveValue("4")
  })
})
