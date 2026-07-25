import { useState, type FormEvent } from "react"

import { ApiError, login } from "../api/client"
import { Notice } from "../components/Notice"

function safeNext(): string { const next = new URLSearchParams(window.location.search).get("next"); return next === "/chat" || next === "/manage" ? next : "" }

export function LoginPage() {
  const [username, setUsername] = useState(""); const [password, setPassword] = useState(""); const [error, setError] = useState<string | null>(null); const [saving, setSaving] = useState(false)
  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => { event.preventDefault(); setSaving(true); setError(null); try { window.location.assign(await login(username.trim(), password, safeNext())) } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "网络连接暂不可用") } finally { setSaving(false) } }
  return <main className="page"><section className="panel login"><p className="brand">ELFIENEST · 家庭精灵巢</p><h1>回来吧，精灵正在等你。</h1><p>登录后进入属于你的聊天与管理空间。</p><form onSubmit={(event) => { void submit(event) }}><label>账号<input autoComplete="username" onChange={(event) => setUsername(event.target.value)} required value={username} /></label><label>密码<input autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} required type="password" value={password} /></label>{error && <Notice kind="error" message={error} />}<button className="button" disabled={saving} type="submit">{saving ? "正在登录…" : "进入 ElfieNest"}</button></form></section></main>
}
