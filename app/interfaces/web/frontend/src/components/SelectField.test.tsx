import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeAll, describe, expect, it, vi } from "vitest"

import { SelectField } from "./SelectField"

describe("SelectField", () => {
  beforeAll(() => {
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
  })

  it("renders an accessible trigger for the selected option", () => {
    render(
      <SelectField
        label="默认登录页"
        onValueChange={() => undefined}
        options={[
          { label: "管理页", value: "manage" },
          { label: "聊天页", value: "chat" },
        ]}
        value="manage"
      />,
    )

    const field = screen.getByRole("group", { name: "默认登录页" })
    const trigger = within(field).getByRole("combobox", { name: "默认登录页" })
    expect(trigger).toHaveTextContent("管理页")
    expect(within(field).getAllByText("默认登录页")).toHaveLength(1)
  })

  it("supports long English portal options, disabled choices, and keyboard selection", async () => {
    const user = userEvent.setup()
    const onValueChange = vi.fn()
    render(
      <SelectField
        label="Default destination after signing in"
        onValueChange={onValueChange}
        options={[
          {
            label: "Available destinations",
            options: [
              { disabled: true, label: "Unavailable archived administration workspace", value: "archive" },
              { label: "Management workspace with a deliberately long English label", value: "manage" },
            ],
          },
        ]}
        value=""
      />,
    )

    const trigger = screen.getByRole("combobox", { name: "Default destination after signing in" })
    trigger.focus()
    await user.keyboard("{Enter}")

    expect(screen.getByRole("listbox")).toBeInTheDocument()
    expect(screen.getByRole("option", { name: "Unavailable archived administration workspace" })).toHaveAttribute("aria-disabled", "true")

    await user.keyboard("{ArrowDown}{Enter}")
    expect(onValueChange).toHaveBeenCalledWith("manage")
    expect(trigger).toHaveFocus()
  })

  it("does not open while the entire field is disabled", async () => {
    const user = userEvent.setup()
    render(
      <SelectField
        disabled
        label="Language preference"
        onValueChange={() => undefined}
        options={[{ label: "English", value: "en-US" }]}
        value="en-US"
      />,
    )

    const trigger = screen.getByRole("combobox", { name: "Language preference" })
    await user.click(trigger)

    expect(trigger).toBeDisabled()
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })
})
