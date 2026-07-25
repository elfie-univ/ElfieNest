import { useEffect, useState } from "react"

import { ApiError, ownerRead, ownerWrite } from "../api/client"
import { Notice } from "./Notice"

export function OwnerFoodPanel({ csrfToken }: { readonly csrfToken: string }) {
  const [catalog, setCatalog] = useState<unknown>(null)
  const [preview, setPreview] = useState<unknown>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const load = async (): Promise<void> => { try { setCatalog(await ownerRead("/api/owner/runtime/foods/")); setError(null) } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "粮食目录加载失败") } }
  useEffect(() => { void load() }, [])
  const generatePreview = async (): Promise<void> => { try { setPreview(await ownerWrite("/api/owner/runtime/foods/update-preview", "POST", csrfToken, { use_llm: false })); setNotice("已生成更新预览；确认后才会应用。") } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "无法生成粮食预览") } }
  const apply = async (): Promise<void> => { if (!window.confirm("确认应用当前粮食更新吗？")) return; try { const result = await ownerWrite("/api/owner/runtime/foods/update-apply", "POST", csrfToken, { confirm: true, candidate: extractCandidate(preview) }); setCatalog(result); setNotice("粮食更新已应用。") } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "粮食更新没有应用") } }
  const rollback = async (): Promise<void> => { if (!window.confirm("确认回滚最近一次粮食更新吗？")) return; try { setCatalog(await ownerWrite("/api/owner/runtime/foods/rollback", "POST", csrfToken, { confirm: true })); setNotice("粮食目录已回滚。") } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "没有可回滚的粮食版本") } }
  return <section className="manage-card manage-card--wide"><div className="manage-head"><div><h2>粮食</h2><p>先生成预览，再确认应用；可回滚最近一次版本。</p></div><button className="button button--quiet" onClick={() => { void load() }} type="button">刷新</button></div>{error && <Notice kind="error" message={error} />}{notice && <Notice message={notice} />}<pre className="manager-json">{catalog === null ? "正在读取粮食目录…" : JSON.stringify(catalog, null, 2)}</pre><div className="manage-actions"><button className="button button--quiet" onClick={() => { void generatePreview() }} type="button">生成更新预览</button><button className="button" disabled={preview === null} onClick={() => { void apply() }} type="button">确认应用</button><button className="button button--quiet" onClick={() => { void rollback() }} type="button">回滚最近版本</button></div>{preview !== null ? <pre className="manager-json">{JSON.stringify(preview, null, 2)}</pre> : null}</section>
}

function extractCandidate(preview: unknown): unknown {
  if (typeof preview !== "object" || preview === null || !("candidate" in preview)) return undefined
  return preview.candidate
}
