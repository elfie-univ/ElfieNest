import { describe, expect, it } from "vitest"

import {
  clampCropRect,
  cropAspectRatio,
  defaultCropRect,
  fitCropRectToAspect,
  squareCropRect,
} from "./profile-capture-crop"

describe("profile capture crop geometry", () => {
  it("starts the square avatar crop around the visible head instead of the raw frame center", () => {
    const crop = defaultCropRect(1000, 600, "square", {
      bottom: 540,
      left: 390,
      right: 610,
      top: 120,
    })

    expect(crop.width).toBe(crop.height)
    expect(crop.x + crop.width / 2).toBeCloseTo(500.5)
    expect(crop.y).toBeLessThan(120)
    expect(crop.y + crop.height).toBeLessThanOrEqual(600)
  })

  it("preserves the selected preset ratio while keeping the box in the image", () => {
    const crop = fitCropRectToAspect({ height: 260, width: 420, x: 760, y: 430 }, 1000, 600, "landscape")

    expect(crop.width / crop.height).toBeCloseTo(cropAspectRatio("landscape"))
    expect(crop.x).toBeGreaterThanOrEqual(0)
    expect(crop.y).toBeGreaterThanOrEqual(0)
    expect(crop.x + crop.width).toBeLessThanOrEqual(1000)
    expect(crop.y + crop.height).toBeLessThanOrEqual(600)
  })

  it("uses the selected region's centered square for an avatar", () => {
    const crop = squareCropRect({ height: 240, width: 360, x: 120, y: 80 }, 1000, 600)

    expect(crop).toEqual({ height: 240, width: 240, x: 180, y: 80 })
  })

  it("clamps keyboard and pointer movement without changing the ratio", () => {
    const crop = clampCropRect({ height: 200, width: 400, x: 900, y: -80 }, 1000, 600, 2)

    expect(crop.width / crop.height).toBeCloseTo(2)
    expect(crop.x + crop.width).toBeLessThanOrEqual(1000)
    expect(crop.y).toBeGreaterThanOrEqual(0)
  })
})
