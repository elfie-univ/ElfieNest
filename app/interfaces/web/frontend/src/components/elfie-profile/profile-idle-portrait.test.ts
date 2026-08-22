import { describe, expect, it } from "vitest"

import { calculateIdlePortraitFrame } from "./profile-idle-portrait"

describe("calculateIdlePortraitFrame", () => {
  it("centers the visible body and fills the stage without centering source padding", () => {
    const frame = calculateIdlePortraitFrame(1600, 900, 720, 1080, {
      bottom: 980,
      left: 180,
      right: 540,
      top: 340,
    })

    expect(frame).not.toBeNull()
    if (frame === null) return
    const visibleCenterX = frame.left + ((180 + 540 + 1) * 0.5 / 720) * frame.width
    const visibleCenterY = frame.top + ((340 + 980 + 1) * 0.5 / 1080) * frame.height
    const visibleHeight = ((980 - 340 + 1) / 1080) * frame.height

    expect(visibleCenterX).toBeCloseTo(800, 4)
    expect(visibleCenterY).toBeCloseTo(450, 4)
    expect(visibleHeight).toBeCloseTo(738, 4)
  })

  it("falls back to the normal image layout when no silhouette was detected", () => {
    expect(calculateIdlePortraitFrame(1600, 900, 720, 1080, null)).toBeNull()
  })
})
