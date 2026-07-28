import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { RefreshButton } from "./RefreshButton"

describe("RefreshButton", () => {
  it("renders page reload actions as accessible click targets", async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<RefreshButton label="刷新状态" onClick={onClick} />)

    const button = screen.getByRole("button", { name: "刷新状态" })
    expect(button).toBeEnabled()
    await user.click(button)
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})
