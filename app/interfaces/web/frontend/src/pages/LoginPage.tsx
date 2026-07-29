import { useState, type FormEvent } from "react"

import { Button } from "@/components/ui/button"
import { ApiError, login, safeLoginNextPath } from "../api/client"
import { Notice } from "../components/Notice"
import { TextField } from "../components/TextField"

function safeNext(): string {
  return safeLoginNextPath(new URLSearchParams(window.location.search).get("next"))
}

export function LoginPage() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      window.location.assign(await login(username.trim(), password, safeNext()))
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "网络连接暂不可用")
    } finally {
      setSaving(false)
    }
  }

  return <main className="page"><section className="panel login"><p className="brand">ELFIENEST · 家庭精灵巢</p><h1>回来吧，精灵正在等你。</h1><p>登录后进入属于你的聊天与管理空间。</p><form onSubmit={(event) => { void submit(event) }}><TextField autoComplete="username" label="账号" onChange={setUsername} required value={username} /><TextField autoComplete="current-password" label="密码" onChange={setPassword} required type="password" value={password} />{error ? <Notice kind="error" message={error} /> : null}<Button className="mt-1 h-11 w-full rounded-xl" disabled={saving} type="submit">{saving ? "正在登录…" : "进入 ElfieNest"}</Button></form></section></main>
}
