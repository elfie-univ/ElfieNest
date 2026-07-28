import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ownerElfies, ownerUsers, ownerWrite, type OwnerElfie } from "../api/client"
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
  elfie_id: "00000001",
  owner: { account_id: "alice", username: "alice" },
  profile: {
    elfie_id: "00000001",
    name: "星尘",
    species_id: "dog",
    gender: null,
    birth_date: null,
    summary: null,
    online_status: "online",
    status: { code: "at_nest", label: "在巢中", tone: "active" },
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
        account_id: "alice",
        username: "alice",
        display_name: "Alice",
        role: "user",
        created_at: "2026-07-26",
        gender: null,
        birth_date: null,
        elfie_count: 1,
        elfie_quota_override: null,
        effective_elfie_limit: 3,
        online_status: "offline",
        avatar_url: null,
      },
    ])
    vi.mocked(ownerElfies).mockResolvedValue([elfie])
    vi.mocked(ownerWrite).mockResolvedValue({})
  })

  it("shows explicit all-filter labels and keeps the initial API request unfiltered", async () => {
    render(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)

    expect(await screen.findByText("星尘")).toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: "所属用户" })).toHaveTextContent("全部用户")
    expect(screen.getByRole("combobox", { name: "物种" })).toHaveTextContent("全部物种")
    expect(screen.getByRole("combobox", { name: "主粮" })).toHaveTextContent("全部主粮")
    expect(screen.getByRole("combobox", { name: "状态" })).toHaveTextContent("全部状态")
    expect(vi.mocked(ownerElfies)).toHaveBeenCalledWith({})
  })

  it("renders the fixed identity-card fields, food rows, and authoritative status", async () => {
    render(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)

    expect(await screen.findByText("星尘")).toBeInTheDocument()
    const card = within(screen.getByRole("article"))
    expect(card.getByText("在巢中")).toBeInTheDocument()
    expect(card.getAllByRole("term").map((node) => node.textContent)).toEqual([
      "姓名",
      "主人姓名",
      "物种",
      "性别",
      "出生日期",
      "领养日期",
      "ID",
      "床位号",
      "主粮",
      "紧急粮",
      "其他粮",
      "简介",
    ])
    expect(card.getAllByText("未登记")).toHaveLength(2)
    expect(card.getByText("2026-07-26")).toBeInTheDocument()
    expect(card.getByText("未分配")).toBeInTheDocument()
    expect(card.getByText("暂无简介")).toBeInTheDocument()
    expect(card.getByText("00000001")).toBeInTheDocument()
    expect(card.getByText("focus")).toBeInTheDocument()
  })

  it("edits food policy inline without making identity fields editable", async () => {
    const user = userEvent.setup()
    render(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)

    await user.click(await screen.findByRole("button", { name: "编辑 星尘" }))

    expect(screen.queryByRole("dialog", { name: "编辑粮食策略" })).not.toBeInTheDocument()
    expect(screen.getAllByRole("combobox", { name: "主粮" })).toHaveLength(2)
    expect(screen.queryByRole("textbox", { name: "姓名" })).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "保存 星尘" }))
    expect(vi.mocked(ownerWrite)).toHaveBeenCalledWith(
      "/api/user/elfies/00000001/food-policy/",
      "PUT",
      "csrf",
      {
        default_food: "standard",
        allowed_foods: ["standard", "focus"],
        fallback_food: "coarse",
      },
    )
  })

  it("uses the frontend demo cards when the legacy APIs return empty lists", async () => {
    vi.mocked(ownerUsers).mockResolvedValue([])
    vi.mocked(ownerElfies).mockResolvedValue([])

    render(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)

    expect(await screen.findByText("Happy")).toBeInTheDocument()
    expect(screen.getByText("后端暂不可用，当前显示演示数据")).toBeInTheDocument()
  })
})
