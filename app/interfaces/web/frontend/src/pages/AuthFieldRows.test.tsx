import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterEach, describe, expect, it, vi } from "vitest"

import * as client from "../api/setup"
import type { SetupStatus } from "../api/setup"
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
    ollama_installed: false,
    model_id: null,
    bed_count: null,
    owner_configured: false,
    offline_configured: false,
    nest_configured: false,
    locked_at: null,
    remote_configured: false,
    remote_skipped: false,
    remote_connection_id: null,
  },
  install: {
    phase: "model_validation",
    action_key: "idle",
    state: "idle",
    progress: 0,
    error_key: null,
  },
  last_error: null,
  steps: [
    { name: "创建账号", number: 1, status: "current", retry_action: null },
    { name: "配置大模型订阅", number: 2, status: "pending", retry_action: null },
    { name: "完成", number: 3, status: "pending", retry_action: null },
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

    expect((await screen.findAllByLabelText("管理员账号")).some((node) => node.tagName === "INPUT")).toBe(true)
    expect(screen.getAllByLabelText("密码").some((node) => node.tagName === "INPUT")).toBe(true)
  })

})
