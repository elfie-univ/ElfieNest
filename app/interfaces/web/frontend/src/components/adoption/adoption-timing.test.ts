import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  adoptionTimingEnabled,
  beginAdoptionTimingPhase,
  markAdoptionTiming,
  readAdoptionTiming,
} from "./adoption-timing"

describe("adoption timing", () => {
  beforeEach(() => {
    window.localStorage.clear()
    delete window.__adoptionTiming
    window.history.pushState({}, "", "/")
    vi.restoreAllMocks()
  })

  it("stays inert while disabled", () => {
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined)
    expect(adoptionTimingEnabled()).toBe(false)

    beginAdoptionTimingPhase("api").end()
    markAdoptionTiming("generationClick")

    const snapshot = readAdoptionTiming()
    expect(snapshot.enabled).toBe(false)
    expect(snapshot.marks).toEqual({})
    expect(snapshot.phases).toEqual({})
    expect(info).not.toHaveBeenCalled()
  })

  it("collects marks and phase durations once enabled", () => {
    vi.spyOn(console, "info").mockImplementation(() => undefined)
    window.localStorage.setItem("elfienest.adoption-timing", "1")

    expect(adoptionTimingEnabled()).toBe(true)
    markAdoptionTiming("generationClick")
    beginAdoptionTimingPhase("api").end()

    const snapshot = readAdoptionTiming()
    expect(snapshot.enabled).toBe(true)
    expect(snapshot.marks["generationClick"]).toBeGreaterThanOrEqual(0)
    expect(snapshot.phases["api"]).toBeGreaterThanOrEqual(0)
  })

  it("can be enabled through the URL flag", () => {
    vi.spyOn(console, "info").mockImplementation(() => undefined)
    window.history.pushState({}, "", "/?adoptionTiming=1")

    expect(adoptionTimingEnabled()).toBe(true)
  })
})
