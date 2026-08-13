import ky from "ky";
import type { ZodType } from "zod";

const client = ky.create({
  prefix: "api/",
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

export async function requestJson<T>(
  path: string,
  schema: ZodType<T>,
  options: RequestOptions = {},
): Promise<T> {
  const response = await client(path, options);
  const payload = await response.json<unknown>();
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
  const payload = await response.json<unknown>();
  if (!response.ok) {
    const detail = (
      typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string"
    ) ? payload.detail : `请求失败（${response.status}）`;
    throw new Error(detail);
  }
  return schema.parse(payload);
}
