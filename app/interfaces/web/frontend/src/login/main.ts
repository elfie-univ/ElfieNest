import ky from "ky"
import { z } from "zod"

import { ApiError, currentUser } from "../shared/api"
import { clearAndMount, element, notice } from "../shared/ui"

const LoginResponseSchema = z.object({ landing_path: z.union([z.literal("/chat"), z.literal("/manage")]) })

function safeNext(): string {
  const next = new URLSearchParams(window.location.search).get("next")
  return next === "/chat" || next === "/manage" ? next : ""
}

async function login(username: string, password: string): Promise<string> {
  const result = await ky.post(`/api/auth/login${safeNext() ? `?next=${safeNext()}` : ""}`, {
    body: new URLSearchParams({ username, password }),
    credentials: "same-origin",
    throwHttpErrors: false
  })
  const raw: unknown = await result.json().catch(() => ({}))
  if (!result.ok) {
    const detail = z.object({ detail: z.string().optional() }).safeParse(raw)
    throw new ApiError(result.status, detail.success && detail.data.detail ? detail.data.detail : "登录未完成")
  }
  return LoginResponseSchema.parse(raw).landing_path
}

function render(): void {
  const page = element("main", "page")
  const card = element("section", "panel login")
  const brand = element("p", "brand")
  brand.textContent = "ELFIENEST · 家庭精灵巢"
  const title = element("h1")
  title.textContent = "回来吧，精灵正在等你。"
  const intro = element("p")
  intro.textContent = "登录后进入属于你的聊天与管理空间。"
  const form = element("form")
  const username = field("账号", "username", "text")
  const password = field("密码", "password", "password")
  const status = element("div")
  const submit = element("button", "button")
  submit.type = "submit"
  submit.textContent = "进入 ElfieNest"
  form.append(username.label, password.label, status, submit)
  form.addEventListener("submit", async (event) => {
    event.preventDefault()
    status.replaceChildren()
    submit.disabled = true
    try {
      window.location.assign(await login(username.input.value.trim(), password.input.value))
    } catch (error: unknown) {
      status.replaceChildren(notice(error instanceof ApiError ? error.message : "网络连接暂不可用", "error"))
    } finally {
      submit.disabled = false
    }
  })
  card.append(brand, title, intro, form)
  page.append(card)
  clearAndMount(page)
}

function field(labelText: string, name: string, type: "text" | "password"): { readonly label: HTMLLabelElement; readonly input: HTMLInputElement } {
  const label = element("label")
  label.textContent = labelText
  const input = element("input")
  input.autocomplete = type === "password" ? "current-password" : "username"
  input.name = name
  input.required = true
  input.type = type
  label.append(input)
  return { label, input }
}

void currentUser().then((user) => { window.location.assign(user.role === "owner" ? "/manage" : "/chat") }).catch(render)
