import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  adminElfies,
  elfieFoodPolicy,
  embodimentSessions,
  ownerRooms,
  ownerUsers,
  updateElfieFoodPolicy,
  type AdminElfie,
} from "../api/client"
import { createI18n } from "../i18n/config"
import { OwnerElfieOverview } from "./OwnerElfieOverview"
import { ToastProvider } from "./ui/toast"

vi.mock("../api/client", async (loadOriginal) => ({
  ...await loadOriginal<typeof import("../api/client")>(),
  adminElfies: vi.fn(),
  elfieFoodPolicy: vi.fn(),
  embodimentSessions: vi.fn(),
  ownerRooms: vi.fn(),
  ownerUsers: vi.fn(),
  updateElfieFoodPolicy: vi.fn(),
}))

const identity = {
  owner: { user_id: 7, account_id: "alice", display_name: "Alice" },
  permissions: { can_view_profile: true, can_view_cognition: false },
  profile: {
    elfie_id: "00000001",
    name: "星尘",
    species_id: "dog",
    gender: null,
    birth_date: null,
    summary: null,
    adopted_at: "2026-07-26T00:00:00Z",
    profile_status: "empty",
    big_five: null,
    personality_tags: [],
    portrait_url: "",
    appearance: null,
  },
} satisfies AdminElfie

const policy = {
  main_food_id: "standard",
  effective_main_food_id: "standard",
  main_food_options: [
    { food_id: "standard", display_name: "标准粮" },
    { food_id: "focus", display_name: "专注粮" },
  ],
  main_food_unavailable: false,
}

function renderOverview() {
  const i18n = createI18n()
  return render(
    <I18nextProvider i18n={i18n}>
      <ToastProvider>
        <OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />
      </ToastProvider>
    </I18nextProvider>,
  )
}

describe("OwnerElfieOverview", () => {
  beforeEach(() => {
    vi.mocked(adminElfies).mockResolvedValue([identity])
    vi.mocked(elfieFoodPolicy).mockResolvedValue(policy)
    vi.mocked(embodimentSessions).mockResolvedValue([
      { elfie_id: "00000001", state: "at_nest", body_id: null },
    ])
    vi.mocked(ownerRooms).mockResolvedValue([{
      id: "local-nest",
      name: "Local Nest",
      desired_bed_count: 4,
      beds: [],
    }])
    vi.mocked(ownerUsers).mockResolvedValue([{
      user_id: 7,
      account_id: "alice",
      display_name: "Alice",
      role: "user",
      created_at: "2026-07-26",
      gender: null,
      birth_date: null,
      elfie_count: 1,
      elfie_quota_override: null,
      effective_elfie_limit: 3,
      presence: "offline",
      last_seen_at: null,
      language: "zh-CN",
      avatar_url: null,
    }])
    vi.mocked(updateElfieFoodPolicy).mockResolvedValue(policy)
  })

  it("composes identity, Food, Nest and Embodiment resources", async () => {
    renderOverview()

    expect(await screen.findByText("星尘")).toBeInTheDocument()
    expect(screen.getByText("在巢中")).toBeInTheDocument()
    expect(screen.getByText("标准粮")).toBeInTheDocument()
    expect(adminElfies).toHaveBeenCalledWith()
    expect(elfieFoodPolicy).toHaveBeenCalledWith("00000001")
    expect(embodimentSessions).toHaveBeenCalledWith()
    expect(ownerRooms).toHaveBeenCalledWith()
  })

  it("keeps the existing inline Food update behavior", async () => {
    const user = userEvent.setup()
    renderOverview()

    await user.click(await screen.findByRole("button", { name: "编辑 星尘" }))
    await user.click(screen.getByRole("button", { name: "保存 星尘" }))

    expect(updateElfieFoodPolicy).toHaveBeenCalledWith("00000001", "standard", "csrf")
  })
})
