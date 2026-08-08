import { act, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement } from "react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError, ownerAssignBed, ownerElfies, ownerRooms, ownerUpdateBedCount, type OwnerElfie } from "../api/client"
import { createI18n } from "../i18n/config"
import type { SupportedLocale } from "../i18n/locale"
import { OwnerNestPanel } from "./OwnerNestPanel"
import { ToastProvider } from "./ui/toast"

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return {
    ...original,
    ownerElfies: vi.fn(),
    ownerAssignBed: vi.fn(),
    ownerRooms: vi.fn(),
    ownerUpdateBedCount: vi.fn(),
  }
})

vi.mock("./ObserverSurface", () => ({
  ObserverSurface: ({ bedCount, roomId }: { readonly bedCount: number; readonly roomId: string }) => <section aria-label="房间 3D 观察" data-bed-count={String(bedCount)} data-room-id={roomId} data-testid="observer-surface" role="region" />,
}))

const happy = {
  elfie_id: "00000001",
  owner: { user_id: 1, account_id: "owner", display_name: "Owner" },
  profile: {
    elfie_id: "00000001",
    name: "Happy",
    species_id: "fox",
    gender: null,
    birth_date: null,
    summary: null,
    online_status: "unknown",
    status: { code: "unknown", label: "状态未知", tone: "muted" },
    portrait_url: "",
    appearance: {},
    big_five: {},
    personality_tags: [],
    nest: { room_name: "Local Nest", bed_name: "01号床", posture: "unknown" },
    embodiment: { state: "at_nest" },
  },
  food_policy: {
    main_food_id: "standard",
    effective_main_food_id: "standard",
    main_food_options: [{ food_id: "standard", display_name: "标准粮" }],
    main_food_unavailable: false,
  },
  created_at: "2026-07-26T00:00:00Z",
} satisfies OwnerElfie

const stardust = {
  ...happy,
  elfie_id: "00000002",
  profile: { ...happy.profile, elfie_id: "00000002", name: "星尘", nest: { room_name: null, bed_name: null, posture: "unknown" } },
} satisfies OwnerElfie

const roomFixture = [{
  id: "local-nest",
  name: "Local Nest",
  desired_bed_count: 4,
  beds: [
    { anchor_id: "dorm-01/bed-01", id: "dorm-01/bed-01", name: "01号床", occupant_id: "00000001", occupant_name: "Happy", occupant_species_id: "fox" },
    { anchor_id: "dorm-01/bed-02", id: "dorm-01/bed-02", name: "02号床", occupant_id: null, occupant_name: null, occupant_species_id: null },
    { anchor_id: "dorm-01/bed-03", id: "dorm-01/bed-03", name: "03号床", occupant_id: null, occupant_name: null, occupant_species_id: null },
    { anchor_id: "dorm-01/bed-04", id: "dorm-01/bed-04", name: "04号床", occupant_id: null, occupant_name: null, occupant_species_id: null },
  ],
}]

function renderWithI18n(ui: ReactElement, locale: SupportedLocale = "zh-CN") {
  const instance = createI18n()
  void instance.changeLanguage(locale)
  document.documentElement.lang = locale
  return { instance, ...render(<I18nextProvider i18n={instance}><ToastProvider>{ui}</ToastProvider></I18nextProvider>) }
}

describe("OwnerNestPanel", () => {
  beforeEach(() => {
    vi.mocked(ownerRooms).mockResolvedValue(roomFixture)
    vi.mocked(ownerElfies).mockResolvedValue([happy, stardust])
    vi.mocked(ownerAssignBed).mockResolvedValue()
    vi.mocked(ownerUpdateBedCount).mockResolvedValue()
  })

  it("migrates the classic floorplan landmarks, bed numbers, and occupants", async () => {
    const { container } = renderWithI18n(<OwnerNestPanel csrfToken="csrf" />)

    expect(await screen.findAllByText("Happy")).not.toHaveLength(0)
    for (const selector of [".room-map", ".nest-floorplan", ".portal-entrance", ".floor-module", ".main-corridor", ".room-entry", ".inner-corridor"]) {
      expect(container.querySelector(selector), selector).not.toBeNull()
    }
    expect(container.querySelectorAll(".floor-bed-unit")).toHaveLength(4)
    for (const number of ["01", "02", "03", "04"]) {
      expect(screen.getByText(number)).toBeInTheDocument()
    }
    expect(screen.getByText("虫洞终端")).toBeInTheDocument()
    expect(screen.getByText("聚餐区")).toBeInTheDocument()
  })

  it("opens the shared observation monitor only from the camera dialog instead of reserving an inline preview", async () => {
    const user = userEvent.setup()
    renderWithI18n(<OwnerNestPanel csrfToken="csrf" />)

    expect(await screen.findByRole("button", { name: "打开预览" })).toBeInTheDocument()
    expect(screen.queryByRole("region", { name: "房间 3D 观察" })).toBeNull()
    expect(screen.getByRole("heading", { name: "房间床位数" })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "打开预览" }))

    expect(screen.getByRole("dialog", { name: "实时房间摄像头" })).toHaveClass("manage-dialog--camera")
    expect(screen.getByRole("dialog", { name: "实时房间摄像头" }).querySelectorAll("[data-slot='observation-monitor']")).toHaveLength(1)
    expect(screen.getByRole("toolbar", { name: "监控工具栏" })).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "房间 3D 观察" })).toBeInTheDocument()
    expect(screen.queryByText("房间 3D 观察")).toBeNull()
    expect(screen.queryByText("在弹窗中进入房间 3D 观察；拖动可查看房间，滚轮或双指缩放。")).toBeNull()
    expect(screen.queryByRole("button", { name: "进入 3D" })).toBeNull()
    expect(screen.getByRole("button", { name: "关闭实时房间摄像头" })).toBeInTheDocument()
    expect(screen.queryByRole("img", { name: "精灵巢实时摄像头画面" })).toBeNull()
  })

  it("passes the canonical owner room id to the runtime observer", async () => {
    const user = userEvent.setup()
    renderWithI18n(<OwnerNestPanel csrfToken="csrf" />)

    await user.click(await screen.findByRole("button", { name: "打开预览" }))

    expect(screen.getByTestId("observer-surface")).toHaveAttribute("data-room-id", "local-nest")
    expect(screen.getByTestId("observer-surface")).toHaveAttribute("data-bed-count", "4")
  })

  it("shows an explicit empty state when the backend returns no room state", async () => {
    vi.mocked(ownerRooms).mockResolvedValue([])
    vi.mocked(ownerElfies).mockResolvedValue([])

    renderWithI18n(<OwnerNestPanel csrfToken="csrf" />)

    expect(await screen.findByText("暂无精灵床位分配")).toBeInTheDocument()
    expect(screen.queryByText("Happy")).not.toBeInTheDocument()
    expect(screen.queryByText("Kettle")).not.toBeInTheDocument()
    expect(screen.queryByText("admin123")).not.toBeInTheDocument()
    expect(screen.queryByText("user123")).not.toBeInTheDocument()
  })

  it("sorts unassigned elfies first and edits only the selected row", async () => {
    const user = userEvent.setup()
    renderWithI18n(<OwnerNestPanel csrfToken="csrf" />)

    const list = await screen.findByRole("list", { name: "床位分配" })
    const rows = within(list).getAllByRole("listitem")
    const firstRow = rows[0]
    const secondRow = rows[1]
    if (!firstRow || !secondRow) throw new Error("床位分配缺少预期行")
    expect(within(firstRow).getByText("星尘")).toBeInTheDocument()
    expect(within(secondRow).getByText("Happy")).toBeInTheDocument()
    await user.click(within(firstRow).getByRole("button", { name: "编辑星尘的床位" }))
    expect(within(firstRow).getByRole("combobox", { name: "星尘 床位" })).toBeInTheDocument()
    expect(within(secondRow).queryByRole("combobox")).not.toBeInTheDocument()
  })

  it("renders English Nest, floorplan, room, bed, and assignment copy", async () => {
    // Given: the Nest API returns stable room, bed, Elfie, and ID values.

    // When: the panel renders in English.
    renderWithI18n(<OwnerNestPanel csrfToken="csrf" />, "en-US")

    // Then: UI chrome is English while entity values stay byte-identical.
    expect(await screen.findByText(/Room layout/)).toBeInTheDocument()
    expect(screen.queryByRole("heading", { name: "Dorm floorplan and beds" })).not.toBeInTheDocument()
    expect(screen.getByText("Dining area")).toBeInTheDocument()
    expect(screen.getAllByText("Happy")).not.toHaveLength(0)
    expect(screen.getByText("01号床")).toBeInTheDocument()
    expect(screen.getByRole("list", { name: "Bed assignments" })).toBeInTheDocument()
  })

  it("preserves the selected assignment editor when locale changes mid-edit", async () => {
    // Given: the unassigned Elfie row is being edited.
    const user = userEvent.setup()
    const { instance } = renderWithI18n(<OwnerNestPanel csrfToken="csrf" />)
    await user.click(await screen.findByRole("button", { name: "编辑星尘的床位" }))
    expect(screen.getByRole("combobox", { name: "星尘 床位" })).toHaveTextContent("未分配")

    // When: locale changes on the mounted panel.
    await act(async () => { await instance.changeLanguage("en-US") })

    // Then: the same entity remains selected with the same assignment value.
    expect(screen.getByRole("combobox", { name: "Bed for 星尘" })).toHaveTextContent("Unassigned")
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument()
  })

  it("localizes invalid bed counts and closes English 409 assignment detail", async () => {
    // Given: English UI and an assignment conflict with backend detail.
    const user = userEvent.setup()
    vi.mocked(ownerAssignBed).mockRejectedValue(new ApiError(409, "该床位已被占用"))
    renderWithI18n(<OwnerNestPanel csrfToken="csrf" />, "en-US")
    const bedCount = await screen.findByRole("textbox", { name: "Bed count" })

    // When: an invalid count is submitted, then an assignment is attempted.
    await user.clear(bedCount)
    await user.type(bedCount, "3")
    await user.tab()
    expect(bedCount).toHaveValue("4")
    const list = screen.getByRole("list", { name: "Bed assignments" })
    const unassigned = within(list).getAllByRole("listitem")[0]
    if (!(unassigned instanceof HTMLElement)) throw new TypeError("Expected unassigned Elfie row")
    await user.click(within(unassigned).getByRole("button", { name: "Edit bed for 星尘" }))
    await user.click(within(unassigned).getByRole("button", { name: "Save" }))

    // Then: the localized conflict fallback is shown without raw detail.
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to save management data.")
    expect(screen.queryByText("该床位已被占用")).not.toBeInTheDocument()
  })

  it("shows an explicit load error without retaining demo occupants", async () => {
    vi.mocked(ownerRooms).mockRejectedValue(new ApiError(503, "巢状态读取失败"))
    vi.mocked(ownerElfies).mockRejectedValue(new ApiError(503, "精灵读取失败"))

    renderWithI18n(<OwnerNestPanel csrfToken="csrf" />)

    expect(await screen.findByRole("alert")).toHaveTextContent("巢状态读取失败")
    expect(screen.queryByText("Happy")).not.toBeInTheDocument()
    expect(screen.queryByText("Kettle")).not.toBeInTheDocument()
    expect(screen.queryByText("admin123")).not.toBeInTheDocument()
    expect(screen.queryByText("user123")).not.toBeInTheDocument()
  })
})
