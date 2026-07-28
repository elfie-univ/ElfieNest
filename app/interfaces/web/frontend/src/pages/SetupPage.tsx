import { useState, type FormEvent } from "react"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { ApiError, setup } from "../api/client"
import { Notice } from "../components/Notice"
import { TextField } from "../components/TextField"

export function SetupPage() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [fallbackAccepted, setFallbackAccepted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await setup(username.trim(), password)
      window.location.assign("/manage")
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "初始化未完成")
    } finally {
      setSaving(false)
    }
  }

  return <main className="page"><section className="panel login"><p className="brand">ELFIENEST · 首次设置</p><h1>先把家安好。</h1><p>创建这个精灵巢唯一的 Owner 账号。首启先使用内置临时对话引擎；进入管理页后可添加并验证模型供应商。</p><form onSubmit={(event) => { void submit(event) }}><TextField autoComplete="username" label="账号" minLength={3} onChange={setUsername} required value={username} /><TextField autoComplete="new-password" label="密码" minLength={6} onChange={setPassword} required type="password" value={password} /><label className="check"><Checkbox checked={fallbackAccepted} className="size-5 border-2 border-[var(--accent)] bg-[var(--surface-field)] data-checked:bg-[var(--accent)]" onCheckedChange={(checked) => setFallbackAccepted(checked === true)} required />我确认先使用内置临时对话引擎，稍后在管理页验证并配置模型。</label>{error ? <Notice kind="error" message={error} /> : null}<Button className="mt-1 h-11 w-full rounded-xl" disabled={saving || !fallbackAccepted} type="submit">{saving ? "正在创建…" : "创建精灵巢"}</Button></form></section></main>
}
