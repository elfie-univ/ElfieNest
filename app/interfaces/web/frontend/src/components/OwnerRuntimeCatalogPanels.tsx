import { useEffect, useState } from "react"
import { z } from "zod"

import { ApiError, ownerRead, ownerWrite } from "../api/client"
import { Notice } from "./Notice"

const ModelSchema = z.object({ model_id: z.string(), provider: z.string(), display_name: z.string(), capabilities: z.array(z.string()), context_window: z.number(), cost_tier: z.number().int(), visible: z.boolean(), active: z.boolean() })
const ToolsSchema = z.object({ tools: z.record(z.string(), z.unknown()) })
type Model = z.infer<typeof ModelSchema>

export function OwnerModelPanel({ csrfToken }: { readonly csrfToken: string }) {
  const [models, setModels] = useState<readonly Model[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const load = async (): Promise<void> => { try { setModels(z.array(ModelSchema).parse(await ownerRead("/api/owner/models/"))); setError(null) } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "模型目录加载失败") } }
  useEffect(() => { void load() }, [])
  const update = async (model: Model, change: { readonly visible?: boolean; readonly cost_tier?: number }): Promise<void> => { try { await ownerWrite(`/api/owner/models/${encodeURIComponent(model.model_id)}`, "PUT", csrfToken, change); setNotice(`${model.display_name} 已保存。`); await load() } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "模型设置没有保存") } }
  const scan = async (): Promise<void> => { try { const result = await ownerWrite("/api/owner/models/scan", "POST", csrfToken); setNotice(`扫描完成：${JSON.stringify(result)}`) } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "本地模型扫描失败") } }
  return <section className="manage-card manage-card--wide"><div className="manage-head"><div><h2>模型</h2><p>管理目录可见性与成本层级；可扫描本地 Ollama 模型。</p></div><div className="manage-actions"><button className="button button--quiet" onClick={() => { void load() }} type="button">刷新</button><button className="button button--quiet" onClick={() => { void scan() }} type="button">扫描本地模型</button></div></div>{error && <Notice kind="error" message={error} />}{notice && <Notice message={notice} />}<div className="catalog-table">{models.map((model) => <article key={model.model_id}><strong>{model.display_name}</strong><small>{model.provider} · {model.active ? "可用" : "未激活"} · {model.capabilities.join("、")}</small><label><input checked={model.visible} onChange={(event) => { void update(model, { visible: event.target.checked }) }} type="checkbox" /> 在管理目录显示</label><label>成本层级<select onChange={(event) => { void update(model, { cost_tier: Number(event.target.value) }) }} value={model.cost_tier}>{[0, 1, 2, 3, 4].map((tier) => <option key={tier} value={tier}>{tier}</option>)}</select></label></article>)}</div></section>
}

export function OwnerToolPanel({ csrfToken }: { readonly csrfToken: string }) {
  const [tools, setTools] = useState<Record<string, unknown>>({})
  const [selectedKey, setSelectedKey] = useState("")
  const [editor, setEditor] = useState("{}")
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const load = async (): Promise<void> => { try { const data = ToolsSchema.parse(await ownerRead("/api/owner/runtime/tools/")); setTools(data.tools); setError(null) } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "工具配置加载失败") } }
  useEffect(() => { void load() }, [])
  const select = (key: string): void => { setSelectedKey(key); setEditor(JSON.stringify(tools[key] ?? {}, null, 2)) }
  const save = async (): Promise<void> => { if (!selectedKey) return; try { const parsed: unknown = JSON.parse(editor); if (!isJsonObject(parsed)) { setError("工具配置必须是 JSON 对象。"); return } await ownerWrite(`/api/owner/runtime/tools/${encodeURIComponent(selectedKey)}`, "PUT", csrfToken, parsed); setNotice("工具配置已保存。"); await load() } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : reason instanceof SyntaxError ? "请输入合法 JSON。" : "工具配置没有保存") } }
  const verify = async (): Promise<void> => { if (!selectedKey) return; try { const result = await ownerWrite(`/api/owner/runtime/tools/${encodeURIComponent(selectedKey)}/verify`, "POST", csrfToken); setNotice(`验证结果：${JSON.stringify(result)}`) } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "工具验证失败") } }
  return <section className="manage-card manage-card--wide"><div className="manage-head"><div><h2>工具</h2><p>所有工具设置和验证均经 Owner API；密钥字段只写不读。</p></div><button className="button button--quiet" onClick={() => { void load() }} type="button">刷新</button></div>{error && <Notice kind="error" message={error} />}{notice && <Notice message={notice} />}<div className="tool-editor"><div className="tool-list">{Object.entries(tools).map(([key, value]) => <button className={selectedKey === key ? "list-row list-row--active" : "list-row"} key={key} onClick={() => select(key)} type="button"><strong>{key}</strong><small>{JSON.stringify(value)}</small></button>)}</div><div><textarea aria-label="工具 JSON 配置" className="manager-json-input" disabled={!selectedKey} onChange={(event) => setEditor(event.target.value)} value={editor} /><div className="manage-actions"><button className="button" disabled={!selectedKey} onClick={() => { void save() }} type="button">保存工具</button><button className="button button--quiet" disabled={!selectedKey} onClick={() => { void verify() }} type="button">验证工具</button></div></div></div></section>
}

function isJsonObject(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value) }
