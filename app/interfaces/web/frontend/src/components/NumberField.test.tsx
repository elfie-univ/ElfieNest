import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it } from "vitest"

import { createI18n } from "../i18n/config"
import { NumberField } from "./NumberField"

function NumberFixture() {
  const [value, setValue] = useState(4)
  return <NumberField label="床位数" max={5} min={1} onChange={setValue} value={value} />
}

describe("NumberField", () => {
  it("steps within bounds and normalizes malformed input on blur", async () => {
    const user = userEvent.setup()
    render(<I18nextProvider i18n={createI18n()}><NumberFixture /></I18nextProvider>)

    const row = screen.getByRole("group", { name: "床位数" })
    const field = screen.getByRole("textbox", { name: "床位数" })
    expect(within(row).getAllByText("床位数")).toHaveLength(1)
    expect(within(row).getByRole("textbox", { name: "床位数" })).toBe(field)
    expect(within(row).getByRole("button", { name: "减少床位数" })).toBeEnabled()

    const increment = screen.getByRole("button", { name: "增加床位数" })
    await user.click(increment)
    expect(field).toHaveValue("5")
    expect(increment).toBeDisabled()
    await user.click(increment)
    expect(field).toHaveValue("5")

    await user.clear(field)
    await user.type(field, "not-a-number")
    await user.tab()
    expect(field).toHaveValue("5")

    await user.click(screen.getByRole("button", { name: "减少床位数" }))
    expect(field).toHaveValue("4")
  })
})
