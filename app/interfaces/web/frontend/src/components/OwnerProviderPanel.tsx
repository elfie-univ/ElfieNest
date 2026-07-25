import { useEffect, useState, type FormEvent } from "react"
import { z } from "zod"

import { ApiError, ownerRead, ownerWrite } from "../api/client"
import { Notice } from "./Notice"

const ProviderSchema = z.object({
  provider_id: z.string(), name: z.string(), display_name: z.string(), api_base: z.string(),
  api_mode: z.string(), auth_type: z.string(), test_model: z.string(), status: z.string(), has_api_key: z.boolean(),
  models: z.array(z.object({ id: z.string(), display_name: z.string() }))
})
type Provider = z.infer<typeof ProviderSchema>
type ProviderDraft = { readonly providerId: string; readonly displayName: string; readonly apiBase: string; readonly apiKey: string; readonly apiMode: string; readonly authType: string; readonly testModel: string; readonly models: string }

const EMPTY_DRAFT: ProviderDraft = { providerId: "", displayName: "", apiBase: "", apiKey: "", apiMode: "chat_completions", authType: "bearer", testModel: "", models: "" }

function draftFor(provider: Provider): ProviderDraft {
  return { providerId: provider.provider_id, displayName: provider.display_name, apiBase: provider.api_base, apiKey: "", apiMode: provider.api_mode, authType: provider.auth_type, testModel: provider.test_model, models: provider.models.map((model) => model.id).join(" | ") }
}

export function OwnerProviderPanel({ csrfToken }: { readonly csrfToken: string }) {
  const [providers, setProviders] = useState<readonly Provider[]>([])
  const [draft, setDraft] = useState<ProviderDraft>(EMPTY_DRAFT)
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const load = async (): Promise<void> => {
    try { setProviders(z.array(ProviderSchema).parse(await ownerRead("/api/owner/providers/"))); setError(null) }
    catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "供应商数据加载失败") }
  }
  useEffect(() => { void load() }, [])
  const change = (key: keyof ProviderDraft, value: string): void => setDraft((current) => ({ ...current, [key]: value }))
  const save = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    try {
      const body = { provider_id: draft.providerId.trim(), display_name: draft.displayName.trim(), api_base: draft.apiBase.trim(), api_key: draft.apiKey, api_mode: draft.apiMode, auth_type: draft.authType, test_model: draft.testModel.trim(), models: draft.models }
      const path = editing ? `/api/owner/providers/${encodeURIComponent(draft.providerId)}` : "/api/owner/providers/"
      await ownerWrite(path, editing ? "PUT" : "POST", csrfToken, body)
      setNotice(editing ? "供应商配置已更新。" : "供应商已创建。")
      setDraft(EMPTY_DRAFT); setEditing(false); await load()
    } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "供应商配置没有保存") }
  }
  const verify = async (providerId: string): Promise<void> => { try { await ownerWrite(`/api/owner/providers/${encodeURIComponent(providerId)}/verify`, "POST", csrfToken); setNotice("连通性验证已完成，请查看运行日志。") } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "连通性验证失败") } }
  const remove = async (providerId: string): Promise<void> => { if (!window.confirm(`确认删除供应商 ${providerId} 吗？`)) return; try { await ownerWrite(`/api/owner/providers/${encodeURIComponent(providerId)}`, "DELETE", csrfToken); setNotice("供应商已删除。"); await load() } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "供应商没有删除") } }
  return <section className="manage-card manage-card--wide">
    <div className="manage-head"><div><h2>供应商</h2><p>密钥仅可写入，读取结果只显示是否已配置。</p></div><button className="button button--quiet" onClick={() => { void load() }} type="button">刷新</button></div>
    {error && <Notice kind="error" message={error} />}{notice && <Notice message={notice} />}
    <div className="provider-summary-grid">{providers.map((provider) => <article className="provider-summary" key={provider.provider_id}><strong>{provider.name}</strong><small>{provider.status} · {provider.has_api_key ? "密钥已配置" : "未配置密钥"}</small><span>{provider.models.map((model) => model.display_name).join("、") || "尚无模型"}</span><div className="manage-actions"><button className="button button--quiet" onClick={() => { setDraft(draftFor(provider)); setEditing(true) }} type="button">编辑</button><button className="button button--quiet" onClick={() => { void verify(provider.provider_id) }} type="button">验证</button><button className="button button--quiet" onClick={() => { void remove(provider.provider_id) }} type="button">删除</button></div></article>)}</div>
    <form className="provider-form" onSubmit={(event) => { void save(event) }}><h3>{editing ? `编辑 ${draft.providerId}` : "添加供应商"}</h3><input disabled={editing} onChange={(event) => change("providerId", event.target.value)} placeholder="供应商 ID" required value={draft.providerId} /><input onChange={(event) => change("displayName", event.target.value)} placeholder="显示名称" value={draft.displayName} /><input onChange={(event) => change("apiBase", event.target.value)} placeholder="API Base URL" type="url" value={draft.apiBase} /><input autoComplete="new-password" onChange={(event) => change("apiKey", event.target.value)} placeholder={editing ? "留空则不变更密钥" : "API 密钥（如需要）"} type="password" value={draft.apiKey} /><select onChange={(event) => change("apiMode", event.target.value)} value={draft.apiMode}><option value="chat_completions">Chat Completions</option><option value="anthropic_messages">Anthropic Messages</option><option value="ollama">Ollama</option></select><select onChange={(event) => change("authType", event.target.value)} value={draft.authType}><option value="bearer">Bearer</option><option value="x-api-key">X-API-Key</option><option value="none">无认证</option></select><input onChange={(event) => change("testModel", event.target.value)} placeholder="连通性测试模型（可选）" value={draft.testModel} /><input onChange={(event) => change("models", event.target.value)} placeholder="模型 ID，以 | 分隔" value={draft.models} /><div className="manage-actions"><button className="button" type="submit">保存供应商</button>{editing && <button className="button button--quiet" onClick={() => { setDraft(EMPTY_DRAFT); setEditing(false) }} type="button">取消编辑</button>}</div></form>
  </section>
}
