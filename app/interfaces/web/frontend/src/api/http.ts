import ky from "ky"
import { z } from "zod"

export class ApiError extends Error {
  public readonly name = "ApiError"

  public constructor(
    readonly status: number,
    message: string,
    readonly validationDetails: readonly ApiValidationDetail[] = [],
    readonly code?: string,
  ) {
    super(message)
  }
}

const ValidationDetailSchema = z.object({
  loc: z.array(z.union([z.string(), z.number()])).optional(),
  msg: z.string(),
  type: z.string().optional(),
})

export type ApiValidationDetail = z.infer<typeof ValidationDetailSchema>

const ErrorPayloadSchema = z.object({
  detail: z.union([z.string(), z.array(ValidationDetailSchema)]).optional(),
  error: z.object({
    code: z.string(),
    message: z.string(),
  }).optional(),
})

function parseApiError(payload: unknown): {
  readonly code?: string
  readonly message: string
  readonly validationDetails: readonly ApiValidationDetail[]
} {
  const parsed = ErrorPayloadSchema.safeParse(payload)
  if (!parsed.success || parsed.data.detail === undefined) {
    const code = parsed.success ? parsed.data.error?.code : undefined
    const result = {
      message: parsed.success ? parsed.data.error?.message ?? "" : "",
      validationDetails: [],
    }
    if (code === undefined) return result
    return {
      ...result,
      code,
    }
  }
  if (typeof parsed.data.detail === "string") {
    return { message: parsed.data.detail, validationDetails: [] }
  }
  return { message: "", validationDetails: parsed.data.detail }
}

export async function requestJson(path: string, init?: RequestInit): Promise<unknown> {
  const response = await ky(path, {
    credentials: "same-origin",
    throwHttpErrors: false,
    ...init,
  })
  const payload: unknown = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = parseApiError(payload)
    throw new ApiError(response.status, error.message, error.validationDetails, error.code)
  }
  return payload
}

export function csrfHeaders(csrfToken: string, json = false): HeadersInit {
  return json
    ? { "Content-Type": "application/json", "X-CSRF-Token": csrfToken }
    : { "X-CSRF-Token": csrfToken }
}

export async function ownerRead(path: string): Promise<unknown> {
  return requestJson(path)
}

export async function ownerWrite(
  path: string,
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  csrfToken: string,
  body?: unknown,
): Promise<unknown> {
  const init: RequestInit = {
    method,
    headers: csrfHeaders(csrfToken, body !== undefined),
  }
  if (body !== undefined) init.body = JSON.stringify(body)
  return requestJson(path, init)
}
