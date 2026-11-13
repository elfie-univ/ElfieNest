export async function prepareNestPreview(signal?: AbortSignal): Promise<void> {
  const response = await fetch("/api/preview/prepare", {method:"POST", signal:signal ?? null});
  if (!response.ok) throw new Error("预览更新失败，请检查服务日志后重试。");
  const result: {ready?: boolean} = await response.json();
  if (result.ready !== true) throw new Error("预览尚未就绪。");
}
