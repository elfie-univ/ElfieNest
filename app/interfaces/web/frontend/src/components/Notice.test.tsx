import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Notice } from "./Notice"

describe("Notice", () => {
  it("announces informational free text as a status without translating it", () => {
    render(<Notice message="A deliberately long English status supplied by its owning page." />)

    expect(screen.getByRole("status")).toHaveTextContent(
      "A deliberately long English status supplied by its owning page.",
    )
  })

  it("announces error free text assertively", () => {
    render(<Notice kind="error" message="Request failed." />)

    expect(screen.getByRole("alert")).toHaveTextContent("Request failed.")
  })
})
