import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { adminElfies, ownerRooms, type AdminElfie } from "../api/client"
import { createI18n } from "../i18n/config"
import { OwnerNestPanel } from "./OwnerNestPanel"
import { ToastProvider } from "./ui/toast"

vi.mock("../api/client", async (loadOriginal) => ({
  ...await loadOriginal<typeof import("../api/client")>(),
  adminElfies: vi.fn(),
  ownerAssignBed: vi.fn(),
  ownerRooms: vi.fn(),
  ownerUpdateBedCount: vi.fn(),
}))

vi.mock("./ObservationMonitor", () => ({
  ObservationMonitor: () => <section aria-label="房间 3D 观察" />,
}))

const identity = {
  owner: { user_id: 1, account_id: "owner", display_name: "Owner" },
  permissions: { can_view_profile: true, can_view_cognition: false },
  profile: {
    elfie_id: "00000001",
    name: "Happy",
    species_id: "fox",
    gender: null,
    birth_date: null,
    summary: null,
    adopted_at: "2026-07-26",
    profile_status: "empty",
    portrait_url: "",
    appearance: null,
    big_five: null,
    personality_tags: [],
  },
} satisfies AdminElfie

describe("OwnerNestPanel", () => {
  beforeEach(() => {
    vi.mocked(adminElfies).mockResolvedValue([identity])
    vi.mocked(ownerRooms).mockResolvedValue([{
      id: "local-nest",
      name: "Local Nest",
      desired_bed_count: 4,
      beds: [{
        anchor_id: "dorm-01/bed-01",
        id: "dorm-01/bed-01",
        name: "Bed 01",
        occupant_id: "00000001",
        occupant_name: "Happy",
        occupant_species_id: "fox",
      }],
    }])
  })

  it("uses the Elfies identity resource beside the Nest resource", async () => {
    const i18n = createI18n()
    render(<I18nextProvider i18n={i18n}><ToastProvider><OwnerNestPanel csrfToken="csrf" /></ToastProvider></I18nextProvider>)

    expect(await screen.findAllByText("Happy")).not.toHaveLength(0)
    expect(adminElfies).toHaveBeenCalledWith()
    expect(ownerRooms).toHaveBeenCalledWith()
  })
})
