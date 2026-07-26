import { useEffect, useState, type FormEvent } from "react"

import { ApiError, ownerRead, ownerWrite } from "../api/client"
import { Notice } from "./Notice"

type OwnerDataPanelProps = {
  readonly title: string
  readonly description: string
  readonly readPath: string
  readonly csrfToken: string
  readonly writePath?: string
}

function renderJson(value: unknown): string { return JSON.stringify(value, null, 2) }

export function OwnerDataPanel({ title, description, readPath, csrfToken, writePath }: OwnerDataPanelProps) {
  const [data, setData] = useState<unknown>(null)
  const [editor, setEditor] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const load = async (): Promise<void> => {
    try { const loaded = await ownerRead(readPath); setData(loaded); setEditor(renderJson(loaded)); setError(null) }
    catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "管理数据加载失败") }
  }
  useEffect(() => { void load() }, [readPath])
  const save = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault(); if (writePath === undefined) return
    try { const body: unknown = JSON.parse(editor); const updated = await ownerWrite(writePath, "PUT", csrfToken, body); setData(updated); setEditor(renderJson(updated)); setNotice("配置已保存。"); setError(null) }
    catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : reason instanceof SyntaxError ? "请输入合法 JSON。" : "配置未保存") }
  }
  return <section className="manage-card"><div className="manage-head"><div><h2>{title}</h2><p>{description}</p></div><button className="button button--quiet" onClick={() => { void load() }} type="button">刷新</button></div>{error && <Notice kind="error" message={error} />}{notice && <Notice message={notice} />}{writePath === undefined ? <pre className="manage-json">{data === null ? "正在加载…" : renderJson(data)}</pre> : <form onSubmit={(event) => { void save(event) }}><textarea aria-label={`${title} JSON 配置`} className="manage-json-input" onChange={(event) => setEditor(event.target.value)} value={editor} /><button className="button" type="submit">保存配置</button></form>}</section>
}
