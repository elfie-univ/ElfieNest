import { useEffect, useState } from "react"
import type { FormEvent, ReactElement, ReactNode } from "react"

import {
  ApiError,
  type ClientUser,
  type NestRoom,
  type OwnerElfie,
  type OwnerUser,
  createManagedUser,
  currentUser,
  loadFoodCatalog,
  logout,
  ownerElfies,
  ownerRooms,
  ownerUsers,
  saveLandingPage
} from "../shared/api"
import { mountProductPage } from "../shared/react_mount"

type ManageState = {
  readonly elfies: readonly OwnerElfie[]
  readonly foods: Record<string, unknown>
  readonly rooms: readonly NestRoom[]
  readonly user: ClientUser
  readonly users: readonly OwnerUser[]
}

async function loadState(): Promise<ManageState> {
  const user = await currentUser()
  if (user.role !== "owner") {
    window.location.assign("/chat")
    throw new ApiError(403, "普通用户不能进入管理页")
  }
  const [users, elfies, rooms, foods] = await Promise.all([
    ownerUsers(),
    ownerElfies(),
    ownerRooms(),
    loadFoodCatalog().catch(() => ({}))
  ])
  return { user, users, elfies, rooms, foods }
}

function ManageCard({ title, description, children }: { readonly title: string; readonly description: string; readonly children: ReactNode }): ReactElement {
  return <article className="manage-card"><h2>{title}</h2><p>{description}</p>{children}</article>
}

function ManagePage(): ReactElement {
  const [state, setState] = useState<ManageState | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")

  useEffect(() => {
    void loadState().then(setState).catch(() => window.location.assign("/login?next=/manage"))
  }, [])

  if (state === null) return <main className="page" />
  const csrfToken = state.user.csrf_token ?? ""
  const landing = state.user.default_landing_page === "chat" ? "chat" : "manage"
  const foodKeys = Object.keys(state.foods).length > 0 ? Object.keys(state.foods) : ["cheap", "standard", "deep", "multimodal", "mock"]

  const saveLanding = async (page: "chat" | "manage"): Promise<void> => {
    try {
      await saveLandingPage(page, csrfToken)
      setNotice("默认页已保存。")
    } catch (error: unknown) {
      setNotice(error instanceof ApiError ? error.message : "设置未保存")
    }
  }
  const createUser = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    try {
      const created = await createManagedUser(username.trim(), password, csrfToken)
      setState({ ...state, users: [...state.users, { ...created, elfie_count: 0 }] })
      setUsername("")
      setPassword("")
      setNotice("普通用户已创建。")
    } catch (error: unknown) {
      setNotice(error instanceof ApiError ? error.message : "用户未创建")
    }
  }
  const leave = async (): Promise<void> => {
    await logout(csrfToken)
    window.location.assign("/login")
  }

  return (
    <main className="page"><section className="panel manage">
      <header className="manage-head"><div><p className="brand">OWNER CONSOLE</p><h1>你好，{state.user.username}</h1></div></header>
      <section className="manage-grid">
        <ManageCard description="Owner 可选择下一次登录的落点。" title="默认打开页面">
          <div className="manage-actions">
            <button className="button" onClick={() => void saveLanding("manage")} type="button">{landing === "manage" ? "管理页（当前）" : "管理页"}</button>
            <button className="button button--quiet" onClick={() => void saveLanding("chat")} type="button">{landing === "chat" ? "聊天页（当前）" : "聊天页"}</button>
          </div>
        </ManageCard>
        <ManageCard description={`当前共 ${state.elfies.length} 位精灵。`} title="精灵总览"><ul className="manage-list">{state.elfies.length === 0 ? <li>还没有已接入精灵。</li> : state.elfies.map((elfie) => <li key={elfie.elfie_id}>{elfie.name} · {elfie.species_id} · {elfie.owner_username ?? "未分配用户"} · {elfie.room_name === null ? "尚未分配精灵巢" : `${elfie.room_name} · ${elfie.bed_name ?? "未分床位"}`}</li>)}</ul></ManageCard>
        <ManageCard description={`系统已配置 ${foodKeys.length} 种粮食路线（cheap, standard, deep, multimodal, mock）。`} title="粮食策略">
          <div className="food-card-grid">
            {foodKeys.map((key) => {
              const recipe = state.foods[key] as { primary?: { model?: string } } | undefined
              const model = recipe?.primary?.model ?? "系统适配模型"
              return (
                <div className="food-item-card" key={key}>
                  <strong>{key.toUpperCase()} 粮食路线</strong>
                  <small>路由模型: {model}</small>
                </div>
              )
            })}
          </div>
        </ManageCard>
        <ManageCard description={`当前 ${state.rooms.length} 个房间。`} title="精灵巢"><ul className="manage-list">{state.rooms.map((room) => <li key={room.id}>{room.name} · {room.beds.filter((bed) => bed.occupant_name !== null).length}/{room.beds.length} 个床位已使用</li>)}</ul></ManageCard>
        <ManageCard description="创建普通用户；每个用户登录后直接进入聊天页。" title="用户管理">
          <ul className="manage-list">{state.users.map((user) => <li key={user.id}>{user.username} · {user.elfie_count} 位精灵</li>)}</ul>
          <form className="manage-form" onSubmit={(event) => void createUser(event)}><input onChange={(event) => setUsername(event.target.value)} placeholder="新用户名" required value={username} /><input onChange={(event) => setPassword(event.target.value)} placeholder="初始密码" required type="password" value={password} /><button className="button" type="submit">创建用户</button></form>
        </ManageCard>
        <ManageCard description="聊天页与管理页共享同一会话。高级模型参数、音效、摄像头与调试工具可在控制台中进一步调节。" title="会话与高级入口"><div className="manage-actions"><a className="button" href="/chat">进入聊天</a><a className="button button--quiet" href="/manage?mode=classic">高级控制台</a><button className="button button--quiet" onClick={() => void leave()} type="button">退出登录</button></div></ManageCard>
      </section>
      {notice === null ? null : <p className="notice">{notice}</p>}
    </section></main>
  )
}

mountProductPage(<ManagePage />)

