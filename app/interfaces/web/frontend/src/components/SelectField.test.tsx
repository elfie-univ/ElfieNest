import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { SelectField } from "./SelectField"

describe("SelectField", () => {
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
})
