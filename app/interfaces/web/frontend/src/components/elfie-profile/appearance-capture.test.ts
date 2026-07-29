import { describe, expect, it, vi } from "vitest"

import {
  captureAppearance,
  type AppearanceCanvasPainter,
  type AppearanceCanvasSurface,
  type AppearanceCaptureInput,
} from "./appearance-capture"

const captureInput: AppearanceCaptureInput = {
  accent: "accent-token",
  background: "background-token",
  fallback: "H",
  foreground: "foreground-token",
  name: "Happy",
  portraitUrl: "",
  scale: 1.25,
  surface: "surface-token",
  yaw: 24,
}

class RecordingPainter implements AppearanceCanvasPainter {
  public fillStyle: string | CanvasGradient | CanvasPattern = ""
  public font = ""
  public lineWidth = 0
  public strokeStyle: string | CanvasGradient | CanvasPattern = ""
  public textAlign: CanvasTextAlign = "start"
  public textBaseline: CanvasTextBaseline = "alphabetic"
  public readonly operations: string[] = []

  public arc(): void { this.operations.push("arc") }
  public beginPath(): void { this.operations.push("beginPath") }
  public clip(): void { this.operations.push("clip") }
  public drawImage(): void { this.operations.push("drawImage") }
  public ellipse(): void { this.operations.push("ellipse") }
  public fill(): void { this.operations.push(`fill:${String(this.fillStyle)}`) }
  public fillRect(): void { this.operations.push(`fillRect:${String(this.fillStyle)}`) }
  public fillText(value: string): void { this.operations.push(`fillText:${value}:${String(this.fillStyle)}`) }
  public restore(): void { this.operations.push("restore") }
  public rotate(angle: number): void { this.operations.push(`rotate:${angle}`) }
  public save(): void { this.operations.push("save") }
  public scale(x: number, y: number): void { this.operations.push(`scale:${x}:${y}`) }
  public stroke(): void { this.operations.push(`stroke:${String(this.strokeStyle)}`) }
  public translate(x: number, y: number): void { this.operations.push(`translate:${x}:${y}`) }
}

function createSurface(painter: AppearanceCanvasPainter, blob: Blob): AppearanceCanvasSurface {
  return {
    height: 0,
    painter,
    toBlob(callback) { callback(blob) },
    width: 0,
  }
}

describe("captureAppearance", () => {
  it("composes theme, transform, fallback, PNG Blob, and preview URL through the real pipeline", async () => {
    // Given: a recording canvas surface and a profile without a portrait.
    const painter = new RecordingPainter()
    const png = new Blob(["fallback"], { type: "image/png" })
    const createObjectUrl = vi.fn(() => "blob:fallback")

    // When: the production composition pipeline creates a capture.
    const result = await captureAppearance(captureInput, {
      createObjectUrl,
      createSurface: () => createSurface(painter, png),
      loadPortrait: () => Promise.resolve(null),
    })

    // Then: tokens, current transform, fallback, and returned Blob remain observable.
    expect(painter.operations).toContain("fillRect:background-token")
    expect(painter.operations).toContain("fill:surface-token")
    expect(painter.operations).toContain("stroke:accent-token")
    expect(painter.operations).toContain("scale:1.25:1.25")
    expect(painter.operations).toContain(`rotate:${24 * Math.PI / 180}`)
    expect(painter.operations).toContain("fillText:H:foreground-token")
    expect(createObjectUrl).toHaveBeenCalledWith(png)
    expect(result).toEqual({ blob: png, previewUrl: "blob:fallback" })
  })

  it("draws the current portrait rather than the initial fallback when loading succeeds", async () => {
    // Given: a loaded current portrait and the recording canvas surface.
    const painter = new RecordingPainter()
    const portrait = document.createElement("img")
    const png = new Blob(["portrait"], { type: "image/png" })

    // When: the same production composition pipeline captures the portrait.
    await captureAppearance(
      { ...captureInput, portraitUrl: "blob:local-avatar" },
      {
        createObjectUrl: () => "blob:portrait",
        createSurface: () => createSurface(painter, png),
        loadPortrait: () => Promise.resolve(portrait),
      },
    )

    // Then: portrait clipping/drawing replaces fallback text.
    expect(painter.operations).toContain("clip")
    expect(painter.operations).toContain("drawImage")
    expect(painter.operations.some((operation) => operation.startsWith("fillText:"))).toBe(false)
  })
})
