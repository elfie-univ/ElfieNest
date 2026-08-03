import { act, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError, ownerElfiePath, ownerElfies, ownerUsers, ownerWrite, type OwnerElfie } from "../api/client"
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

Object.defineProperty(HTMLElement.prototype, "hasPointerCapture", { configurable: true, value: () => false })
Object.defineProperty(HTMLElement.prototype, "setPointerCapture", { configurable: true, value: () => undefined })
Object.defineProperty(HTMLElement.prototype, "releasePointerCapture", { configurable: true, value: () => undefined })
Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: () => undefined })

const elfie = {
  elfie_id: "00000001",
  owner: { user_id: 7, account_id: "alice", display_name: "Alice" },
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
    main_food_id: "standard",
    effective_main_food_id: "standard",
    main_food_options: [
      { food_id: "standard", display_name: "标准粮" },
      { food_id: "focus", display_name: "专注粮" },
    ],
    main_food_unavailable: false,
  },
  created_at: "2026-07-26T00:00:00Z",
} satisfies OwnerElfie

const memberElfie = {
  ...elfie,
  elfie_id: "00000002",
  owner: { user_id: 42, account_id: "member42", display_name: "Member" },
  profile: { ...elfie.profile, elfie_id: "00000002", name: "成员精灵" },
} satisfies OwnerElfie

const memberUser = {
  user_id: 42,
  account_id: "member42",
  display_name: "Member",
  role: "user" as const,
  created_at: "2026-07-27",
  gender: null,
  birth_date: null,
  elfie_count: 1,
  elfie_quota_override: null,
  effective_elfie_limit: 3,
  presence: "offline" as const,
  last_seen_at: null,
  language: "zh-CN",
  avatar_url: null,
}

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

  it("orders Elfie cards by ascending numeric ID", async () => {
    // Given: the backend returns Elfies in a different order than their registration IDs.
    vi.mocked(ownerElfies).mockResolvedValue([memberElfie, elfie])

    // When: the overview renders.
    renderWithI18n(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)
    const cards = await screen.findAllByRole("article")

    // Then: the oldest/lowest ID is shown first, independent of display name.
    expect(cards.map((card) => card.querySelectorAll(".elfie-id-card__identity dd")[6]?.textContent)).toEqual([
      "00000001",
      "00000002",
    ])
  })

  it("renders the fixed identity-card fields, food rows, and authoritative status", async () => {
    renderWithI18n(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)

    expect(await screen.findByText("星尘")).toBeInTheDocument()
    const card = within(screen.getByRole("article"))
    expect(card.getByText("在巢中")).toBeInTheDocument()
    expect(card.getAllByRole("term").map((node) => node.textContent)).toEqual([
      "姓名",
      "主人",
      "物种",
      "性别",
      "出生日期",
      "领养日期",
      "ID",
      "床位号",
      "主粮",
      "简介",
    ])
    expect(card.getAllByText("未登记")).toHaveLength(2)
    expect(card.getByText("2026-07-26")).toBeInTheDocument()
    expect(card.getByText("未分配")).toBeInTheDocument()
    expect(card.getByText("暂无简介")).toBeInTheDocument()
    expect(card.getByText("00000001")).toBeInTheDocument()
    expect(card.getByText("标准粮")).toBeInTheDocument()
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
        main_food_id: "standard",
      },
    )
  })

  it("shows an explicit empty state when the APIs return empty lists", async () => {
    vi.mocked(ownerUsers).mockResolvedValue([])
    vi.mocked(ownerElfies).mockResolvedValue([])

    renderWithI18n(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)

    expect(await screen.findByText("没有符合筛选条件的精灵。")).toBeInTheDocument()
    expect(screen.queryByText("Happy")).not.toBeInTheDocument()
    expect(screen.queryByText("Kettle")).not.toBeInTheDocument()
    expect(screen.queryByText("admin123")).not.toBeInTheDocument()
    expect(screen.queryByText("user123")).not.toBeInTheDocument()
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
    expect(screen.getByText("标准粮")).toBeInTheDocument()
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
    expect(screen.getByText("标准粮")).toBeInTheDocument()
  })

  it("shows an explicit error state without retaining demo identities", async () => {
    // Given: an API failure includes natural-language Chinese detail.
    vi.mocked(ownerElfies).mockRejectedValue(new ApiError(503, "后端精灵读取失败"))

    // When: the overview loads.
    renderWithI18n(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)

    // Then: the backend error is visible and demo data is absent.
    expect(await screen.findByRole("alert")).toHaveTextContent("后端精灵读取失败")
    expect(screen.queryByText("Happy")).not.toBeInTheDocument()
    expect(screen.queryByText("Kettle")).not.toBeInTheDocument()
    expect(screen.queryByText("admin123")).not.toBeInTheDocument()
    expect(screen.queryByText("user123")).not.toBeInTheDocument()
  })

  it("filters by the numeric Owner user id and keeps display-name labels", async () => {
    const user = userEvent.setup()
    vi.mocked(ownerUsers).mockResolvedValue([
      {
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
      },
      memberUser,
    ])
    vi.mocked(ownerElfies).mockImplementation(async (filters = {}) => filters.ownerUserId === 42 ? [memberElfie] : [elfie, memberElfie])

    renderWithI18n(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)
    expect(await screen.findByText("成员精灵")).toBeInTheDocument()

    await user.click(screen.getByRole("combobox", { name: "所属用户" }))
    await user.click(await screen.findByRole("option", { name: "Member" }))

    expect(await screen.findByText("成员精灵")).toBeInTheDocument()
    expect(screen.queryByText("星尘")).not.toBeInTheDocument()
    expect(vi.mocked(ownerElfies)).toHaveBeenCalledWith({ ownerUserId: 42 })
    expect(ownerElfiePath({ ownerUserId: 42 })).toBe("/api/owner/elfies?owner_user_id=42")
  })

  it("uses account id when an Owner display name is absent", async () => {
    const user = userEvent.setup()
    vi.mocked(ownerUsers).mockResolvedValue([{ ...memberUser, display_name: null }])
    vi.mocked(ownerElfies).mockResolvedValue([{ ...memberElfie, owner: { ...memberElfie.owner, display_name: null } }])

    renderWithI18n(<OwnerElfieOverview csrfToken="csrf" onCountChange={vi.fn()} />)
    await user.click(await screen.findByRole("combobox", { name: "所属用户" }))

    expect(await screen.findByRole("option", { name: "member42" })).toBeInTheDocument()
    const memberName = await screen.findByText("成员精灵")
    const memberCard = memberName.closest("article")
    if (!(memberCard instanceof HTMLElement)) throw new TypeError("Expected an Elfie identity card")
    expect(within(memberCard).getByText("member42")).toBeInTheDocument()
  })
})
