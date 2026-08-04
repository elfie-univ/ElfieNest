import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it } from "vitest"

import { createI18n } from "../i18n/config"
import { LoginPage } from "./LoginPage"
import { SetupPage } from "./SetupPage"

describe("auth and adoption field rows", () => {
  it("renders login fields as horizontal field rows with unique labels", () => {
    render(
      <I18nextProvider i18n={createI18n()}>
        <LoginPage />
      </I18nextProvider>,
    )

    expect(screen.getAllByLabelText("账号").some((node) => node.tagName === "INPUT")).toBe(true)
    expect(screen.getAllByLabelText("密码").some((node) => node.tagName === "INPUT")).toBe(true)
  })

  it("keeps setup true fields as rows while the fallback confirmation remains checkbox copy", () => {
    render(<SetupPage />)

    expect(screen.getByLabelText("管理员账号")).toBeInTheDocument()
    expect(screen.getByLabelText("密码")).toBeInTheDocument()
  })

})
