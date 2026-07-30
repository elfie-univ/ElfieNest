import ky from "ky"
import { z } from "zod"

export class ApiError extends Error {
  public readonly name = "ApiError"

  public constructor(readonly status: number, message: string) {
    super(message)
  }
}

const ValidationDetailSchema = z.object({
  loc: z.array(z.union([z.string(), z.number()])).optional(),
  msg: z.string(),
  type: z.string().optional(),
})

const ErrorPayloadSchema = z.object({
  detail: z.union([z.string(), z.array(ValidationDetailSchema)]).optional(),
})

const FIELD_LABELS: Readonly<Record<string, string>> = {
  provider_id: "供应商 ID",
  api_base: "API Base URL",
  api_key: "API 密钥",
  display_name: "显示名称",
  test_model: "测试模型",
}

function validationMessage(type: string | undefined, fallback: string): string {
  if (type === "missing") return "不能为空"
  if (type === "string_pattern_mismatch") return "格式不正确"
  if (type === "string_too_long") return "内容过长"
  if (type === "url_parsing") return "不是有效地址"
  return fallback
}

function apiErrorMessage(payload: unknown): string {
  const parsed = ErrorPayloadSchema.safeParse(payload)
  if (!parsed.success || parsed.data.detail === undefined) return "请求未完成"
  if (typeof parsed.data.detail === "string") return parsed.data.detail
  const messages = parsed.data.detail.map((item) => {
    const field = item.loc?.at(-1)
    const label = typeof field === "string" ? FIELD_LABELS[field] ?? field : undefined
    const message = validationMessage(item.type, item.msg)
    return label ? `${label}：${message}` : message
  })
  return messages.length > 0 ? messages.join("；") : "请求未完成"
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
