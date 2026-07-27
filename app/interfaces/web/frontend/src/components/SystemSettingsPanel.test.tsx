import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ownerRead, ownerWrite } from "../api/client"
import { SystemSettingsPanel } from "./SystemSettingsPanel"

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return { ...original, ownerRead: vi.fn(), ownerWrite: vi.fn() }
})

const engine = { tick_interval_sec: 1.5, max_elfies_per_room: null }
const adoption = { max_elfies_per_user: 3, allowed_species_ids: ["dog", "fox"], personality_presets_enabled: {} }
const security = { session_ttl_days: 7, rate_limit: { max_attempts: 5, window_seconds: 60 } }

describe("SystemSettingsPanel", () => {
  beforeEach(() => {
    vi.mocked(ownerRead).mockImplementation(async (path) => {
      if (path.endsWith("/engine")) return engine
      if (path.endsWith("/adoption")) return adoption
      return security
    })
    vi.mocked(ownerWrite).mockResolvedValue({})
  })

  it("uses shared bounded controls and saves only the selected module", async () => {
    const user = userEvent.setup()
    render(<SystemSettingsPanel csrfToken="csrf" />)

    await user.click(await screen.findByRole("button", { name: "增加运行 Tick（秒）" }))
    await user.click(screen.getByRole("button", { name: "保存引擎设置" }))

    await waitFor(() => expect(vi.mocked(ownerWrite)).toHaveBeenCalledWith(
      "/api/owner/system/engine",
      "PUT",
      "csrf",
      { tick_interval_sec: 1.6, max_elfies_per_room: null },
    ))
    expect(screen.getByRole("checkbox", { name: "狗" })).toBeChecked()
    expect(screen.getByRole("checkbox", { name: "狐狸" })).toBeChecked()
  })
})
