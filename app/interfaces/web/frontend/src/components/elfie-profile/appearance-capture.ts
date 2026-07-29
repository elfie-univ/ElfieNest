export type AppearanceCaptureInput = {
  readonly accent: string
  readonly background: string
  readonly fallback: string
  readonly foreground: string
  readonly name: string
  readonly portraitUrl: string
  readonly scale: number
  readonly surface: string
  readonly yaw: number
}

export type AppearanceCapture = {
  readonly blob: Blob
  readonly previewUrl: string
}

export type AppearanceCaptureAdapter = (
  input: AppearanceCaptureInput,
) => Promise<AppearanceCapture>

export interface AppearanceCanvasPainter {
  fillStyle: string | CanvasGradient | CanvasPattern
  font: string
  lineWidth: number
  strokeStyle: string | CanvasGradient | CanvasPattern
  textAlign: CanvasTextAlign
  textBaseline: CanvasTextBaseline
  arc(x: number, y: number, radius: number, start: number, end: number): void
  beginPath(): void
  clip(): void
  drawImage(image: CanvasImageSource, x: number, y: number, width: number, height: number): void
  ellipse(x: number, y: number, rx: number, ry: number, rotation: number, start: number, end: number): void
  fill(): void
  fillRect(x: number, y: number, width: number, height: number): void
  fillText(text: string, x: number, y: number): void
  restore(): void
  rotate(angle: number): void
  save(): void
  scale(x: number, y: number): void
  stroke(): void
  translate(x: number, y: number): void
}

export interface AppearanceCanvasSurface {
  height: number
  readonly painter: AppearanceCanvasPainter
  width: number
  toBlob(callback: BlobCallback, type: string): void
}

export type AppearanceCaptureDependencies = {
  readonly createObjectUrl: (blob: Blob) => string
  readonly createSurface: () => AppearanceCanvasSurface
  readonly loadPortrait: (source: string) => Promise<HTMLImageElement | null>
}

export class AppearanceCaptureError extends Error {
  public readonly reason: "context" | "encoding"

  public constructor(reason: "context" | "encoding") {
    super(reason === "context" ? "Canvas context is unavailable" : "PNG encoding failed")
    this.name = "AppearanceCaptureError"
    this.reason = reason
  }
}

export async function captureAppearance(
  input: AppearanceCaptureInput,
  dependencies: AppearanceCaptureDependencies = defaultCaptureDependencies,
): Promise<AppearanceCapture> {
  const canvas = dependencies.createSurface()
  canvas.width = 960
  canvas.height = 600
  const context = canvas.painter

  context.fillStyle = input.background || "Canvas"
  context.fillRect(0, 0, canvas.width, canvas.height)
  drawPlatform(context, input)

  context.save()
  context.translate(canvas.width / 2, canvas.height / 2 - 18)
  context.scale(input.scale, input.scale)
  context.rotate(input.yaw * Math.PI / 180)
  const portrait = await dependencies.loadPortrait(input.portraitUrl)
  if (portrait === null) {
    drawFallback(context, input)
  } else {
    drawPortrait(context, portrait, input)
  }
  context.restore()

  const blob = await encodePng(canvas)
  return {
    blob,
    previewUrl: dependencies.createObjectUrl(blob),
  }
}

function drawPlatform(
  context: AppearanceCanvasPainter,
  input: AppearanceCaptureInput,
): void {
  context.fillStyle = input.surface || "Canvas"
  context.beginPath()
  context.ellipse(480, 492, 214, 46, 0, 0, Math.PI * 2)
  context.fill()
  context.strokeStyle = input.accent || "CanvasText"
  context.lineWidth = 4
  context.stroke()
}

function drawFallback(
  context: AppearanceCanvasPainter,
  input: AppearanceCaptureInput,
): void {
  context.fillStyle = input.surface || "Canvas"
  context.beginPath()
  context.arc(0, 0, 152, 0, Math.PI * 2)
  context.fill()
  context.fillStyle = input.foreground || "CanvasText"
  context.font = "700 154px system-ui"
  context.textAlign = "center"
  context.textBaseline = "middle"
  context.fillText(input.fallback, 0, 7)
}

function drawPortrait(
  context: AppearanceCanvasPainter,
  portrait: HTMLImageElement,
  input: AppearanceCaptureInput,
): void {
  context.save()
  context.beginPath()
  context.arc(0, 0, 152, 0, Math.PI * 2)
  context.clip()
  context.drawImage(portrait, -152, -152, 304, 304)
  context.restore()
  context.strokeStyle = input.accent || "CanvasText"
  context.lineWidth = 5
  context.beginPath()
  context.arc(0, 0, 152, 0, Math.PI * 2)
  context.stroke()
}

function loadPortrait(source: string): Promise<HTMLImageElement | null> {
  if (source.length === 0) {
    return Promise.resolve(null)
  }
  return new Promise((resolve) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => resolve(null)
    image.src = source
  })
}

function encodePng(canvas: AppearanceCanvasSurface): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob === null) {
        reject(new AppearanceCaptureError("encoding"))
        return
      }
      resolve(blob)
    }, "image/png")
  })
}

const defaultCaptureDependencies: AppearanceCaptureDependencies = {
  createObjectUrl: (blob) => URL.createObjectURL(blob),
  createSurface: createCanvasSurface,
  loadPortrait,
}

function createCanvasSurface(): AppearanceCanvasSurface {
  const canvas = document.createElement("canvas")
  const painter = canvas.getContext("2d")
  if (painter === null) {
    throw new AppearanceCaptureError("context")
  }
  return {
    get height() { return canvas.height },
    set height(value: number) { canvas.height = value },
    painter,
    toBlob(callback, type) { canvas.toBlob(callback, type) },
    get width() { return canvas.width },
    set width(value: number) { canvas.width = value },
  }
}
