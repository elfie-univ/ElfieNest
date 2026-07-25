import { useEffect, useState } from "react"
import type { FormEvent, ReactElement } from "react"
import ky from "ky"
import { z } from "zod"

import { ApiError, currentUser } from "../shared/api"
import { mountProductPage } from "../shared/react_mount"

const LoginResponseSchema = z.object({
  landing_path: z.union([z.literal("/chat"), z.literal("/manage")])
})

function safeNext(): string {
  const next = new URLSearchParams(window.location.search).get("next")
  return next === "/chat" || next === "/manage" ? next : ""
}

async function login(username: string, password: string): Promise<string> {
  const next = safeNext()
  const response = await ky.post(`/api/auth/login${next === "" ? "" : `?next=${next}`}`, {
    body: new URLSearchParams({ username, password }),
    credentials: "same-origin",
    throwHttpErrors: false
  })
  const raw: unknown = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = z.object({ detail: z.string().optional() }).safeParse(raw)
    throw new ApiError(response.status, detail.success && detail.data.detail ? detail.data.detail : "登录未完成")
  }
  return LoginResponseSchema.parse(raw).landing_path
}

function LoginPage(): ReactElement {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [notice, setNotice] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    void currentUser()
      .then((user) => window.location.assign(user.role === "owner" ? "/manage" : "/chat"))
      .catch(() => undefined)
  }, [])

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    setNotice(null)
    setSubmitting(true)
    try {
      window.location.assign(await login(username.trim(), password))
    } catch (error: unknown) {
      setNotice(error instanceof ApiError ? error.message : "网络连接暂不可用")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="page">
      <section className="panel login">
        <p className="brand">ELFIENEST · 家庭精灵巢</p>
        <h1>回来吧，精灵正在等你。</h1>
        <p>登录后进入属于你的聊天与管理空间。</p>
        <form onSubmit={(event) => void submit(event)}>
          <label>
            账号
            <input autoComplete="username" name="username" onChange={(event) => setUsername(event.target.value)} required value={username} />
          </label>
          <label>
            密码
            <input autoComplete="current-password" name="password" onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
          </label>
          {notice === null ? null : <p className="notice notice--error">{notice}</p>}
          <button className="button" disabled={submitting} type="submit">进入 ElfieNest</button>
        </form>
      </section>
    </main>
  )
}

mountProductPage(<LoginPage />)
