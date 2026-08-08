import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, describe, expect, it, vi } from "vitest"

import * as client from "../api/client"
import type { SetupStatus } from "../api/client"
import { createI18n } from "../i18n/config"
import { LoginPage } from "./LoginPage"
import { SetupPage } from "./SetupPage"

const freshSetupStatus: SetupStatus = {
  complete: false,
  current_step: 1,
  need_setup: true,
  locked: false,
  csrf_token: "setup-csrf",
  draft: {
    owner_account_id: null,
    display_name: null,
    password_configured: false,
    use_local_ollama: null,
    ollama_installed: true,
    model_id: null,
    bed_count: null,
    owner_configured: false,
    offline_configured: false,
    nest_configured: false,
    locked_at: null,
  },
  install: {
    phase: "owner",
    action_key: "idle",
    state: "idle",
    progress: 0,
    error_key: null,
  },
  last_error: null,
  steps: [
    { name: "Owner", number: 1, status: "current" },
    { name: "Offline", number: 2, status: "pending" },
    { name: "Nest", number: 3, status: "pending" },
    { name: "Review", number: 4, status: "pending" },
  ],
}

describe("auth and adoption field rows", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("renders login fields as horizontal field rows with unique labels", () => {
    render(
      <I18nextProvider i18n={createI18n()}>
        <LoginPage />
      </I18nextProvider>,
    )

    expect(screen.getAllByLabelText("账号").some((node) => node.tagName === "INPUT")).toBe(true)
    expect(screen.getAllByLabelText("密码").some((node) => node.tagName === "INPUT")).toBe(true)
  })

  it("keeps setup true fields as rows while the fallback confirmation remains checkbox copy", async () => {
    const user = userEvent.setup()
    vi.spyOn(client, "setupStatus").mockResolvedValue(freshSetupStatus)
    vi.spyOn(client, "setupModelCatalog").mockResolvedValue([])
    render(<SetupPage />)

    await user.click(await screen.findByRole("button", { name: "开始" }))

    expect((await screen.findAllByLabelText("超级管理员账号")).some((node) => node.tagName === "INPUT")).toBe(true)
    expect(screen.getAllByLabelText("密码").some((node) => node.tagName === "INPUT")).toBe(true)
  })

})
