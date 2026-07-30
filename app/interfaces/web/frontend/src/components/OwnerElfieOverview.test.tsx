import { act, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError, ownerElfies, ownerUsers, ownerWrite, type OwnerElfie } from "../api/client"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
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

function renderWithI18n(ui: ReactElement, locale: SupportedLocale = "zh-CN") {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  document.documentElement.lang = locale
  return { instance, ...render(<I18nextProvider i18n={instance}>{ui}</I18nextProvider>) }
}

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
    renderWithI18n(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)

    expect(await screen.findByText("星尘")).toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: "所属用户" })).toHaveTextContent("全部用户")
    expect(screen.getByRole("combobox", { name: "物种" })).toHaveTextContent("全部物种")
    expect(screen.getByRole("combobox", { name: "主粮" })).toHaveTextContent("全部主粮")
    expect(screen.getByRole("combobox", { name: "状态" })).toHaveTextContent("全部状态")
    expect(vi.mocked(ownerElfies)).toHaveBeenCalledWith({})
  })

  it("renders the fixed identity-card fields, food rows, and authoritative status", async () => {
    renderWithI18n(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)

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
    renderWithI18n(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)

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

    renderWithI18n(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)

    expect(await screen.findByText("Happy")).toBeInTheDocument()
    expect(screen.getByText("后端暂不可用，当前显示演示数据")).toBeInTheDocument()
  })

  it("renders English Elfie identity copy while preserving names, IDs, species, and food keys", async () => {
    // Given: an Elfie has a backend status label in Chinese.
    vi.mocked(ownerElfies).mockResolvedValue([{ ...elfie, profile: { ...elfie.profile, status: { code: "mystery", label: "后端未知状态", tone: "muted" } } }])

    // When: the overview renders in English.
    renderWithI18n(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />, "en-US")

    // Then: chrome and unknown status are localized without changing entity values.
    expect(await screen.findByRole("heading", { name: "All Elfies" })).toBeInTheDocument()
    expect(screen.getByText("Unknown status")).toBeInTheDocument()
    expect(screen.queryByText("后端未知状态")).not.toBeInTheDocument()
    expect(screen.getByText("星尘")).toBeInTheDocument()
    expect(screen.getByText("00000001")).toBeInTheDocument()
    expect(screen.getByText("dog")).toBeInTheDocument()
    expect(screen.getByText("standard")).toBeInTheDocument()
  })

  it("preserves the selected Elfie and food edit state when locale changes", async () => {
    // Given: the real card is editing a selected food value.
    const user = userEvent.setup()
    const { instance } = renderWithI18n(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)
    await user.click(await screen.findByRole("button", { name: "编辑 星尘" }))
    const food = screen.getAllByRole("combobox", { name: "主粮" })[1]
    if (!(food instanceof HTMLElement)) throw new TypeError("Expected editable food selector")

    // When: locale switches on the mounted overview.
    await act(async () => { await instance.changeLanguage("en-US") })

    // Then: the same card stays in edit mode with its selection unchanged.
    expect(screen.getAllByRole("combobox", { name: "Staple food" })).toHaveLength(2)
    expect(screen.getByRole("button", { name: "Save 星尘" })).toBeInTheDocument()
    expect(screen.getByText("standard")).toBeInTheDocument()
  })

  it("hides backend load detail behind the English demo fallback", async () => {
    // Given: an API failure includes natural-language Chinese detail.
    vi.mocked(ownerElfies).mockRejectedValue(new ApiError(503, "后端精灵读取失败"))

    // When: the overview loads in English.
    renderWithI18n(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />, "en-US")

    // Then: demo data remains available and backend detail is not rendered.
    expect(await screen.findByText("Happy")).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveTextContent("The backend is unavailable, so demo data is shown.")
    expect(screen.queryByText("后端精灵读取失败")).not.toBeInTheDocument()
  })
})
