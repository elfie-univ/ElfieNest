import { afterEach, describe, expect, it, vi } from "vitest"

import type { SetupStatus } from "./setup"
import { setupStatus } from "./setup"

const { requestJsonMock } = vi.hoisted(() => ({ requestJsonMock: vi.fn() }))

vi.mock("./http", () => ({
  csrfHeaders: vi.fn(),
  requestJson: requestJsonMock,
}))

function status(): SetupStatus {
  return {
    need_setup: true,
    complete: false,
    current_step: 1,
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
    },
    steps: [
      { number: 1, name: "Owner", status: "current", retry_action: null },
      { number: 2, name: "Offline", status: "pending", retry_action: null },
      { number: 3, name: "Nest", status: "pending", retry_action: null },
      { number: 4, name: "Install", status: "pending", retry_action: null },
    ],
    last_error: null,
    install: {
      phase: "owner",
      action_key: "idle",
      state: "idle",
      progress: 0,
      error_key: null,
    },
  }
}

describe("setup API client", () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it("always reloads Setup status without using a browser cache entry", async () => {
    requestJsonMock.mockResolvedValue(status())

    await expect(setupStatus()).resolves.toMatchObject({ csrf_token: "setup-csrf" })
    expect(requestJsonMock).toHaveBeenCalledWith(
      "/api/v1/setup/status",
      { cache: "no-store" },
    )
  })
})
