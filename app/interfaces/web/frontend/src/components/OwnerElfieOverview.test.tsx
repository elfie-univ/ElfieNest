import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ownerElfies, ownerUsers, type OwnerElfie } from "../api/client"
import { OwnerElfieOverview } from "./OwnerElfieOverview"

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return {
    ...original,
    ownerElfies: vi.fn(),
    ownerUsers: vi.fn(),
    ownerWrite: vi.fn(),
  }
})

const elfie = {
  elfie_id: "elfie_with_a_very_long_stable_identifier_001",
  owner: { user_id: 2, username: "alice" },
  profile: {
    elfie_id: "elfie_with_a_very_long_stable_identifier_001",
    name: "星尘",
    species_id: "dog",
    gender: null,
    birth_date: null,
    summary: null,
    online_status: "unknown",
    portrait_url: "",
    appearance: {},
    big_five: {},
    personality_tags: [],
    nest: { room_name: "主精灵巢", bed_name: null, posture: "unknown" },
    embodiment: { state: "at_nest" },
  },
  food_policy: {
    default_food: "standard",
    allowed_foods: ["standard", "focus"],
    fallback_food: "coarse",
  },
  created_at: "2026-07-26T00:00:00Z",
} satisfies OwnerElfie

describe("OwnerElfieOverview", () => {
  beforeEach(() => {
    vi.mocked(ownerUsers).mockResolvedValue([
      {
        id: 2,
        username: "alice",
        display_name: "Alice",
        role: "user",
        created_at: "2026-07-26",
        elfie_count: 1,
        elfie_quota_override: null,
        effective_elfie_limit: 3,
        online_status: "unknown",
        avatar_url: null,
      },
    ])
    vi.mocked(ownerElfies).mockResolvedValue([elfie])
  })

  it("shows explicit all-filter labels and keeps the initial API request unfiltered", async () => {
    render(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)

    expect(await screen.findByText("星尘")).toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: "按用户筛选精灵" })).toHaveTextContent("全部用户")
    expect(screen.getByRole("combobox", { name: "按物种筛选精灵" })).toHaveTextContent("全部物种")
    expect(screen.getByRole("combobox", { name: "按粮食筛选精灵" })).toHaveTextContent("全部粮食")
    expect(screen.getByRole("combobox", { name: "按具身状态筛选精灵" })).toHaveTextContent("全部状态")
    expect(vi.mocked(ownerElfies)).toHaveBeenCalledWith({})
  })

  it("renders the fixed identity-card fields with honest missing-data fallbacks", async () => {
    render(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)

    expect(await screen.findByText("星尘")).toBeInTheDocument()
    const card = within(screen.getByRole("article"))
    for (const label of ["姓名", "主人", "物种", "性别", "出生日期", "床位号", "唯一 ID", "简介"]) {
      expect(card.getByText(label)).toBeInTheDocument()
    }
    expect(card.getAllByText("未登记")).toHaveLength(2)
    expect(card.getByText("未分配")).toBeInTheDocument()
    expect(card.getByText("暂无简介")).toBeInTheDocument()
    expect(card.getByText("elfie_with_a_very_long_stable_identifier_001")).toBeInTheDocument()
  })

  it("opens the shared food editor without making identity fields editable", async () => {
    const user = userEvent.setup()
    render(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)

    await user.click(await screen.findByRole("button", { name: "编辑 星尘 的粮食策略" }))

    expect(screen.getByRole("dialog", { name: "编辑粮食策略" })).toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: "选择默认粮食" })).toBeInTheDocument()
    expect(screen.queryByRole("textbox", { name: "姓名" })).not.toBeInTheDocument()
  })
})
