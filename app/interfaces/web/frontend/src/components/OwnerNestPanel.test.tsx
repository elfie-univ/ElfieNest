import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ownerCameraStatus, ownerElfies, ownerRooms, type OwnerElfie } from "../api/client"
import { OwnerNestPanel } from "./OwnerNestPanel"

vi.mock("../api/client", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../api/client")>()
  return {
    ...original,
    ownerCameraStatus: vi.fn(),
    ownerElfies: vi.fn(),
    ownerRooms: vi.fn(),
    ownerWrite: vi.fn(),
  }
})

const happy = {
  elfie_id: "00000001",
  owner: { account_id: "owner", username: "owner" },
  profile: {
    elfie_id: "00000001",
    name: "Happy",
    species_id: "fox",
    gender: null,
    birth_date: null,
    summary: null,
    online_status: "online",
    status: { code: "at_nest", label: "在巢中", tone: "active" },
    portrait_url: "",
    appearance: {},
    big_five: {},
    personality_tags: [],
    nest: { room_name: "Local Nest", bed_name: "01号床", posture: "unknown" },
    embodiment: { state: "at_nest" },
  },
  food_policy: { default_food: "standard", allowed_foods: ["standard"], fallback_food: "coarse" },
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

describe("OwnerNestPanel", () => {
  beforeEach(() => {
    vi.mocked(ownerRooms).mockResolvedValue(roomFixture)
    vi.mocked(ownerElfies).mockResolvedValue([happy, stardust])
    vi.mocked(ownerCameraStatus).mockResolvedValue({
      online: false,
      labels: ["整体总览", "区域俯视 01-04"],
      active_index: 0,
      desired_index: 0,
      frame_version: 0,
      layout_syncing: false,
      desired_bed_count: 4,
      reported_bed_count: 4,
    })
  })

  it("migrates the classic floorplan beds, room labels, and occupants", async () => {
    render(<OwnerNestPanel csrfToken="csrf" />)

    expect(await screen.findAllByText("Happy")).not.toHaveLength(0)
    for (const number of ["01", "02", "03", "04"]) {
      expect(screen.getByText(number)).toBeInTheDocument()
    }
    expect(screen.getByText("01号床")).toBeInTheDocument()
    expect(screen.getByText("虫洞终端")).toBeInTheDocument()
    expect(screen.getByText("聚餐区")).toBeInTheDocument()
  })

  it("keeps the camera preview inside the dialog instead of the sidebar", async () => {
    const user = userEvent.setup()
    render(<OwnerNestPanel csrfToken="csrf" />)

    expect(await screen.findByRole("button", { name: "打开预览" })).toBeInTheDocument()
    expect(screen.queryByText("摄像头离线")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "打开预览" }))
    const dialog = screen.getByRole("dialog", { name: "实时房间摄像头" })
    expect(within(dialog).getByText("摄像头离线")).toBeInTheDocument()
    expect(within(dialog).getByRole("option", { name: /整体总览/ })).toBeInTheDocument()
    expect(within(dialog).getByRole("option", { name: /区域俯视 01-04/ })).toBeInTheDocument()
  })

  it("keeps the bed count control and save action in one compact row", async () => {
    render(<OwnerNestPanel csrfToken="csrf" />)

    const form = await screen.findByRole("form", { name: "床位数量设置" })
    expect(within(form).getByRole("textbox", { name: "床位数" })).toBeInTheDocument()
    expect(within(form).getByRole("button", { name: "保存布局" })).toBeInTheDocument()
    expect(within(form).queryByText("期望床位")).not.toBeInTheDocument()
  })

  it("sorts unassigned elfies first and edits only the selected row", async () => {
    const user = userEvent.setup()
    render(<OwnerNestPanel csrfToken="csrf" />)

    const list = await screen.findByRole("list", { name: "床位分布" })
    const rows = within(list).getAllByRole("listitem")
    const firstRow = rows[0]
    const secondRow = rows[1]
    if (!firstRow || !secondRow) throw new Error("床位分布缺少预期行")
    expect(within(firstRow).getByText("星尘")).toBeInTheDocument()
    expect(within(secondRow).getByText("Happy")).toBeInTheDocument()
    await user.click(within(firstRow).getByRole("button", { name: "编辑星尘的床位" }))
    expect(within(firstRow).getByRole("combobox", { name: "星尘 床位" })).toBeInTheDocument()
    expect(within(secondRow).queryByRole("combobox")).not.toBeInTheDocument()
  })
})
