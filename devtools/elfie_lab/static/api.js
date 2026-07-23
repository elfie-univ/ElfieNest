export const MAX_MEDIA_BYTES = 5 * 1024 * 1024;

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function api(path, options = {}) {
  const { headers: suppliedHeaders = {}, ...requestOptions } = options;
  const headers = new Headers(suppliedHeaders);
  const bodyIsForm = requestOptions.body instanceof FormData;
  if (requestOptions.body && !bodyIsForm && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...requestOptions, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(payload.detail || `请求失败 (${response.status})`, response.status);
  }
  return payload;
}

export async function uploadMedia(elfieId, file) {
  if (file.size > MAX_MEDIA_BYTES) {
    throw new ApiError("图片不能超过 5 MiB", 0);
  }
  const form = new FormData();
  form.append("file", file, file.name);
  return api(`/api/elfies/${encodeURIComponent(elfieId)}/media`, {
    method: "POST",
    body: form,
  });
}
