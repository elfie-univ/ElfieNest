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

export class AppearanceCaptureError extends Error {
  public readonly reason: "context" | "encoding"

  public constructor(reason: "context" | "encoding") {
    super(reason === "context" ? "Canvas context is unavailable" : "PNG encoding failed")
    this.name = "AppearanceCaptureError"
    this.reason = reason
  }
}
