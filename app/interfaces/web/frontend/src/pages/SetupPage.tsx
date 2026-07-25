import { useState, type FormEvent } from "react"

import { ApiError, setup } from "../api/client"
import { Notice } from "../components/Notice"

export function SetupPage() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [fallbackAccepted, setFallbackAccepted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault(); setSaving(true); setError(null)
    try { await setup(username.trim(), password); window.location.assign("/manage") }
    catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "初始化未完成") }
    finally { setSaving(false) }
  }
  return <main className="page"><section className="panel login"><p className="brand">ELFIENEST · 首次设置</p><h1>先把家安好。</h1><p>创建这个精灵巢唯一的 Owner 账号。首启先使用内置临时对话引擎；进入管理页后可添加并验证模型供应商。</p><form onSubmit={(event) => { void submit(event) }}><label>账号<input autoComplete="username" minLength={3} onChange={(event) => setUsername(event.target.value)} required value={username} /></label><label>密码<input autoComplete="new-password" minLength={6} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} /></label><label className="check"><input checked={fallbackAccepted} onChange={(event) => setFallbackAccepted(event.target.checked)} required type="checkbox" />我确认先使用内置临时对话引擎，稍后在管理页验证并配置模型。</label>{error && <Notice kind="error" message={error} />}<button className="button" disabled={saving || !fallbackAccepted} type="submit">{saving ? "正在创建…" : "创建精灵巢"}</button></form></section></main>
}
