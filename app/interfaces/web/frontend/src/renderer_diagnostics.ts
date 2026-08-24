type RendererErrorOrigin =
  | "window_error"
  | "unhandled_rejection"
  | "react_uncaught"
  | "react_recoverable"

type RendererDiagnosticPayload = Readonly<{
  origin: RendererErrorOrigin
  error_type: string
  message: string
  stack: string
  occurrences: number
  suppressed_count: number
}>

const MAX_ERROR_SIGNATURES = 256
const errorOccurrences = new Map<string, number>()

function redactRendererDiagnostic(value: string): string {
  return value
    .replace(/(https?:\/\/[^\s?]+)\?[^\s]+/giu, "$1?<redacted>")
    .replace(
      /(["']?\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|token|nonce|password|secret|authorization)\b["']?\s*[:=]\s*)(["'])[^\r\n]*?\2/giu,
      "$1$2<redacted>$2",
    )
    .replace(
      /(["']?\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|token|nonce|password|secret|authorization)\b["']?\s*[:=]\s*)(?!["'])(?:Bearer\s+)?[^\s,;}\]]+/giu,
      "$1<redacted>",
    )
    .replace(/\bBearer\s+[A-Za-z0-9._~+\-/]+=*/giu, "Bearer <redacted>")
}

function errorText(error: unknown): Readonly<{
  errorType: string
  message: string
  stack: string
}> {
  if (error instanceof Error) {
    return {
      errorType: error.name,
      message: error.message,
      stack: error.stack ?? "",
    }
  }
  let message: string
  try {
    message = String(error)
  } catch {
    message = "unprintable renderer error"
  }
  return {
    errorType: typeof error,
    message,
    stack: "",
  }
}

export function reportRendererError(
  origin: RendererErrorOrigin,
  error: unknown,
  supplementalStack = "",
): void {
  const bridge = window.elfienestDesktop
  if (bridge === undefined) return
  const normalized = errorText(error)
  const stack = [normalized.stack, supplementalStack].filter(Boolean).join("\n")
  const errorType = redactRendererDiagnostic(normalized.errorType).slice(0, 128)
  const message = redactRendererDiagnostic(normalized.message).slice(0, 2_048)
  const redactedStack = redactRendererDiagnostic(stack).slice(0, 8_192)
  const signature = [origin, errorType, message, redactedStack.split("\n", 1)[0]].join("\u0000")
  const occurrences = (errorOccurrences.get(signature) ?? 0) + 1
  if (!errorOccurrences.has(signature) && errorOccurrences.size >= MAX_ERROR_SIGNATURES) {
    const oldest = errorOccurrences.keys().next().value as string | undefined
    if (oldest !== undefined) errorOccurrences.delete(oldest)
  }
  errorOccurrences.set(signature, occurrences)
  if (!isPowerOfTwo(occurrences)) return
  const payload: RendererDiagnosticPayload = {
    origin,
    error_type: errorType,
    message,
    stack: redactedStack,
    occurrences,
    suppressed_count: occurrences <= 2 ? 0 : (occurrences / 2) - 1,
  }
  try {
    bridge.reportRendererError(payload)
  } catch {
    // Diagnostics must never become a second renderer failure.
  }
}

export function resetRendererDiagnosticSamplingForTests(): void {
  errorOccurrences.clear()
}

function isPowerOfTwo(value: number): boolean {
  return value > 0 && Number.isInteger(Math.log2(value))
}

export function installGlobalRendererDiagnostics(): () => void {
  const onError = (event: ErrorEvent): void => {
    reportRendererError("window_error", event.error ?? new Error(event.message))
  }
  const onUnhandledRejection = (event: PromiseRejectionEvent): void => {
    reportRendererError("unhandled_rejection", event.reason)
  }
  window.addEventListener("error", onError)
  window.addEventListener("unhandledrejection", onUnhandledRejection)
  return () => {
    window.removeEventListener("error", onError)
    window.removeEventListener("unhandledrejection", onUnhandledRejection)
  }
}
