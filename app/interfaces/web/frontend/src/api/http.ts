import ky from "ky"
import { z } from "zod"

export class ApiError extends Error {
  public readonly name = "ApiError"

  public constructor(readonly status: number, message: string) {
    super(message)
  }
}

export async function requestJson(path: string, init?: RequestInit): Promise<unknown> {
  const response = await ky(path, {
    credentials: "same-origin",
    throwHttpErrors: false,
    ...init,
  })
  const payload: unknown = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = z.object({ detail: z.string().optional() }).safeParse(payload)
    const message = detail.success && detail.data.detail ? detail.data.detail : ""
    throw new ApiError(response.status, message)
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
  method: "POST" | "PUT" | "DELETE",
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
