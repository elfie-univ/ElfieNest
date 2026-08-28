import ky from "ky";
import type { ZodType } from "zod";

const client = ky.create({
  prefix: "/api/",
  timeout: 10_000,
  retry: 0,
  throwHttpErrors: false,
});

type RequestOptions = Readonly<{
  readonly method?: "get" | "post" | "put" | "patch" | "delete";
  readonly json?: unknown;
  readonly timeout?: number;
}>;

type FormRequestOptions = Readonly<{
  readonly method: "post" | "put" | "patch";
  readonly form: FormData;
}>;

async function readResponsePayload(response: Response): Promise<unknown> {
  const raw = await response.text();
  if (!raw.trim()) return null;
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    if (!response.ok) {
      const summary = raw.replace(/\s+/g, " ").trim().slice(0, 180);
      throw new Error(summary ? `请求失败（${response.status}）：${summary}` : `请求失败（${response.status}）`);
    }
    throw new Error(`服务返回了无法识别的数据（${response.status}）`);
  }
}

export async function requestJson<T>(
  path: string,
  schema: ZodType<T>,
  options: RequestOptions = {},
): Promise<T> {
  const response = await client(path, options);
  const payload = await readResponsePayload(response);
  if (!response.ok) {
    const detail = (
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "string"
    ) ? payload.detail : `请求失败（${response.status}）`;
    throw new Error(detail);
  }
  return schema.parse(payload);
}

export async function requestFormJson<T>(
  path: string,
  schema: ZodType<T>,
  options: FormRequestOptions,
): Promise<T> {
  const response = await client(path, { method: options.method, body: options.form });
  const payload = await readResponsePayload(response);
  if (!response.ok) {
    const detail = (
      typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string"
    ) ? payload.detail : `请求失败（${response.status}）`;
    throw new Error(detail);
  }
  return schema.parse(payload);
}
