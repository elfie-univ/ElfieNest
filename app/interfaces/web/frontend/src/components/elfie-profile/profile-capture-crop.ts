import type { AppearanceCapture } from "./appearance-capture"
import { calculateVisibleFrameBounds, type VisibleFrameBounds } from "./profile-godot-preview"

export const CROP_ASPECTS = {
  square: { height: 1, label: "1:1", width: 1 },
  landscape: { height: 9, label: "16:9", width: 16 },
  portrait: { height: 16, label: "9:16", width: 9 },
} as const

export type CropAspect = keyof typeof CROP_ASPECTS

export type CropRect = {
  readonly height: number
  readonly width: number
  readonly x: number
  readonly y: number
}

export type CropImageInfo = {
  readonly height: number
  readonly visibleBounds: VisibleFrameBounds | null
  readonly width: number
}

export function cropAspectRatio(aspect: CropAspect): number {
  const preset = CROP_ASPECTS[aspect]
  return preset.width / preset.height
}

export function defaultCropRect(
  width: number,
  height: number,
  aspect: CropAspect,
  visibleBounds: VisibleFrameBounds | null = null,
): CropRect {
  const safeWidth = Math.max(1, Math.floor(width))
  const safeHeight = Math.max(1, Math.floor(height))
  const ratio = cropAspectRatio(aspect)
  const visibleWidth = visibleBounds === null ? 0 : visibleBounds.right - visibleBounds.left + 1
  const visibleHeight = visibleBounds === null ? 0 : visibleBounds.bottom - visibleBounds.top + 1
  const squareReference = Math.max(
    visibleWidth * 1.14,
    Math.min(visibleHeight * 0.6, safeHeight * 0.57),
    Math.min(safeWidth, safeHeight) * 0.38,
  )
  let cropHeight = Math.min(safeHeight, Math.max(1, squareReference))
  let cropWidth = cropHeight * ratio
  if (cropWidth > safeWidth) {
    cropWidth = safeWidth
    cropHeight = cropWidth / ratio
  }

  const centerX = visibleBounds === null
    ? safeWidth * 0.5
    : (visibleBounds.left + visibleBounds.right + 1) * 0.5
  const top = visibleBounds === null ? safeHeight * 0.08 : visibleBounds.top - cropHeight * 0.03
  return clampCropRect({
    height: cropHeight,
    width: cropWidth,
    x: centerX - cropWidth * 0.5,
    y: top,
  }, safeWidth, safeHeight, ratio)
}

export function fitCropRectToAspect(
  rect: CropRect,
  width: number,
  height: number,
  aspect: CropAspect,
): CropRect {
  const safeWidth = Math.max(1, Math.floor(width))
  const safeHeight = Math.max(1, Math.floor(height))
  const ratio = cropAspectRatio(aspect)
  const centerX = rect.x + rect.width * 0.5
  const centerY = rect.y + rect.height * 0.5
  let cropWidth = Math.max(1, rect.width)
  let cropHeight = cropWidth / ratio
  if (cropHeight > safeHeight) {
    cropHeight = safeHeight
    cropWidth = cropHeight * ratio
  }
  if (cropWidth > safeWidth) {
    cropWidth = safeWidth
    cropHeight = cropWidth / ratio
  }
  return clampCropRect({
    height: cropHeight,
    width: cropWidth,
    x: centerX - cropWidth * 0.5,
    y: centerY - cropHeight * 0.5,
  }, safeWidth, safeHeight, ratio)
}

export function squareCropRect(rect: CropRect, width: number, height: number): CropRect {
  const size = Math.min(rect.width, rect.height, width, height)
  return clampCropRect({
    height: size,
    width: size,
    x: rect.x + (rect.width - size) * 0.5,
    y: rect.y + (rect.height - size) * 0.5,
  }, width, height, 1)
}

export function clampCropRect(rect: CropRect, width: number, height: number, ratio: number): CropRect {
  const safeWidth = Math.max(1, width)
  const safeHeight = Math.max(1, height)
  let cropWidth = Math.max(1, Math.min(rect.width, safeWidth))
  let cropHeight = Math.max(1, Math.min(rect.height, safeHeight))
  if (Math.abs(cropWidth / cropHeight - ratio) > 0.001) {
    cropHeight = Math.min(cropHeight, cropWidth / ratio)
    cropWidth = cropHeight * ratio
    if (cropWidth > safeWidth) {
      cropWidth = safeWidth
      cropHeight = cropWidth / ratio
    }
  }
  return {
    height: cropHeight,
    width: cropWidth,
    x: Math.max(0, Math.min(safeWidth - cropWidth, rect.x)),
    y: Math.max(0, Math.min(safeHeight - cropHeight, rect.y)),
  }
}

export async function inspectCapture(capture: AppearanceCapture): Promise<CropImageInfo> {
  const image = await loadImage(capture.previewUrl)
  const width = image.naturalWidth
  const height = image.naturalHeight
  if (width < 1 || height < 1) throw new Error("invalid_capture_dimensions")
  const canvas = document.createElement("canvas")
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext("2d")
  if (context === null) return { height, visibleBounds: null, width }
  context.drawImage(image, 0, 0, width, height)
  let visibleBounds: VisibleFrameBounds | null = null
  try {
    visibleBounds = calculateVisibleFrameBounds(width, height, context.getImageData(0, 0, width, height).data)
  } catch {
    visibleBounds = null
  }
  return { height, visibleBounds, width }
}

export async function cropCapture(capture: AppearanceCapture, rect: CropRect): Promise<AppearanceCapture> {
  const sourceUrl = URL.createObjectURL(capture.blob)
  try {
    const image = await loadImage(sourceUrl)
    const canvas = document.createElement("canvas")
    const width = Math.max(1, Math.round(rect.width))
    const height = Math.max(1, Math.round(rect.height))
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext("2d")
    if (context === null) throw new Error("canvas_context_unavailable")
    context.drawImage(image, rect.x, rect.y, rect.width, rect.height, 0, 0, width, height)
    const blob = await canvasToBlob(canvas)
    return { blob, previewUrl: URL.createObjectURL(blob) }
  } finally {
    URL.revokeObjectURL(sourceUrl)
  }
}

function loadImage(source: string): Promise<HTMLImageElement> {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error("invalid_capture_image"))
    image.src = source
  })
}

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob === null) {
        reject(new Error("png_encoding_failed"))
        return
      }
      resolve(blob)
    }, "image/png")
  })
}
