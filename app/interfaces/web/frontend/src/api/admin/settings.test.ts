import { beforeEach, describe, expect, it, vi } from "vitest"

import { ownerRead, ownerWrite } from "../http"
import {
  elfieSettings,
  environmentSettings, updateEnvironmentSettings,
  runtimeSettings,
  securitySettings,
  updateElfieSettings,
  type ElfieSettings,
} from "./settings"

vi.mock("../http", () => ({ ownerRead: vi.fn(), ownerWrite: vi.fn() }))

describe("administrator Settings API boundary", () => {
  beforeEach(() => vi.clearAllMocks())

  it("parses each existing settings resource through its dedicated schema", async () => {
    vi.mocked(ownerRead).mockImplementation(async (path) => {
      if (path.endsWith("/runtime")) return { tick_interval_sec: 1.5 }
      if (path.endsWith("/elfies")) return {
        max_elfies_per_user: 3,
        personality_presets_enabled: {},
      }
      if (path.endsWith("/security")) return {
        session_ttl_days: 7,
        rate_limit: { max_attempts: 5, window_seconds: 60 },
      }
      throw new Error(`unexpected path: ${path}`)
    })

    await expect(runtimeSettings()).resolves.toEqual({ tick_interval_sec: 1.5 })
    await expect(elfieSettings()).resolves.toMatchObject({ max_elfies_per_user: 3 })
    await expect(securitySettings()).resolves.toMatchObject({ session_ttl_days: 7 })
  })

  it("writes the existing Elfie settings resource with CSRF", async () => {
    const settings: ElfieSettings = {
      max_elfies_per_user: 4,
      personality_presets_enabled: {},
    }
    vi.mocked(ownerWrite).mockResolvedValue(settings)

    await updateElfieSettings(settings, "csrf")

    expect(ownerWrite).toHaveBeenCalledWith(
      "/api/v1/admin/settings/elfies",
      "PATCH",
      "csrf",
      settings,
    )
  })

  it("rejects values outside the backend Settings contract", async () => {
    vi.mocked(ownerRead).mockResolvedValue({
      max_elfies_per_user: 33,
        personality_presets_enabled: {},
    })

    await expect(elfieSettings()).rejects.toThrow()
  })

  it("rejects the retired per-species administrator field", async () => {
    vi.mocked(ownerRead).mockResolvedValue({
      max_elfies_per_user: 3,
      allowed_species_ids: ["saevi"],
      personality_presets_enabled: {},
    })

    await expect(elfieSettings()).rejects.toThrow()
  })

  it("validates environment settings and writes them to the manager resource with CSRF", async () => {
    const settings = { daylight_source: "manual" as const, sunrise_time: "06:00", sunset_time: "18:00", rest_time: "00:00", latitude: null, longitude: null }
    const result = { settings, today: { date: "2026-11-03", timezone: "UTC", sunrise_time: "06:00", sunset_time: "18:00", condition: "normal" } }
    vi.mocked(ownerWrite).mockResolvedValue(result)
    await expect(updateEnvironmentSettings(settings, "csrf")).resolves.toEqual(result)
    expect(ownerWrite).toHaveBeenCalledWith("/api/v1/admin/settings/environment", "PUT", "csrf", { settings })
    vi.mocked(ownerRead).mockResolvedValue({ ...result, settings: { ...settings, daylight_source: "unknown" } })
    await expect(environmentSettings()).rejects.toThrow()
  })
})
