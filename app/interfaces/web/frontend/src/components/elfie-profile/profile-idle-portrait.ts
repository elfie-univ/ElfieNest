import type { VisibleFrameBounds } from "./profile-godot-preview"

export type IdlePortraitFrame = {
  readonly height: number
  readonly left: number
  readonly top: number
  readonly width: number
}

const TARGET_VISIBLE_HEIGHT = 0.82
const MAX_VISIBLE_WIDTH = 0.72

/**
 * Frames the visible silhouette instead of the source canvas. The stored
 * full-body PNGs intentionally keep capture padding, so centering the raw
 * bitmap centers the padding rather than the character.
 */
export function calculateIdlePortraitFrame(
  stageWidth: number,
  stageHeight: number,
  imageWidth: number,
  imageHeight: number,
  visibleBounds: VisibleFrameBounds | null,
): IdlePortraitFrame | null {
  if (
    stageWidth <= 0
    || stageHeight <= 0
    || imageWidth <= 0
    || imageHeight <= 0
    || visibleBounds === null
  ) return null

  const baseScale = Math.min(stageWidth / imageWidth, stageHeight / imageHeight)
  const visibleWidth = Math.max(1, visibleBounds.right - visibleBounds.left + 1) * baseScale
  const visibleHeight = Math.max(1, visibleBounds.bottom - visibleBounds.top + 1) * baseScale
  const scale = Math.min(
    stageHeight * TARGET_VISIBLE_HEIGHT / visibleHeight,
    stageWidth * MAX_VISIBLE_WIDTH / visibleWidth,
  )
  const visibleCenterX = (visibleBounds.left + visibleBounds.right + 1) * 0.5 * baseScale
  const visibleCenterY = (visibleBounds.top + visibleBounds.bottom + 1) * 0.5 * baseScale

  return {
    height: imageHeight * baseScale * scale,
    left: stageWidth * 0.5 - visibleCenterX * scale,
    top: stageHeight * 0.5 - visibleCenterY * scale,
    width: imageWidth * baseScale * scale,
  }
}
