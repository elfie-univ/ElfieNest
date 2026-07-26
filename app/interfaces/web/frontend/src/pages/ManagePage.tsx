import { useEffect, useState, type FormEvent, type ReactNode } from "react"

import { ApiError, createManagedUser, ownerUsers, type OwnerUser } from "../api/client"
import { Notice } from "../components/Notice"
import { CameraPreview } from "../components/CameraPreview"
import { OwnerDataPanel } from "../components/OwnerDataPanel"
import { OwnerElfieOverview } from "../components/OwnerElfieOverview"
import { OwnerFoodPanel } from "../components/OwnerFoodPanel"
import { OwnerNestPanel } from "../components/OwnerNestPanel"
import { OwnerProviderPanel } from "../components/OwnerProviderPanel"
import { OwnerModelPanel, OwnerToolPanel } from "../components/OwnerRuntimeCatalogPanels"
import { ManagerSidebar } from "../components/ManagerSidebar"
import { useSession } from "../stores/session"
import { IconCatalogPage } from "./IconCatalogPage"
import { isManagerTab, managerNavItem, type ManagerTab } from "./managerNavigation"

function initialTab(): ManagerTab {
  const requested = new URLSearchParams(window.location.search).get("section")
  return isManagerTab(requested) ? requested : "monitor"
}

function Card({ title, description, children }: { readonly title: string; readonly description: string; readonly children: ReactNode }) {
  return <article className="manage-card"><h2>{title}</h2><p>{description}</p>{children}</article>
}

export function ManagePage() {
  const { user, loading, refresh } = useSession()
  const [tab, setTab] = useState<ManagerTab>(initialTab)
  const [elfieCount, setElfieCount] = useState(0)
  if (loading) return <main className="page"><p className="empty">正在验证会话…</p></main>
  if (user?.role !== "owner") { window.location.assign(user === null ? "/login?next=/manage" : "/chat"); return <main /> }
  if (new URLSearchParams(window.location.search).get("icon-catalog") === "1") return <IconCatalogPage />
  const csrfToken = user.csrf_token ?? ""
  const chooseTab = (next: ManagerTab): void => {
    setTab(next)
    window.history.replaceState({}, "", `/manage?section=${next}`)
  }
  const currentItem = managerNavItem(tab)
  return <main className="app-page"><section className="manage-workbench manage-workbench--console">
    <ManagerSidebar activeTab={tab} onSelect={chooseTab} onUserUpdated={refresh} user={user} />
    <section className="panel manage manage--console">
      <header className="manage-console-head"><div><p className="brand">{currentItem?.label ?? "OWNER CONSOLE"}</p><h1>{currentItem?.label ?? "管理台"}</h1><p>管理、聊天与领养保持分离；这里仅展示 Owner 的系统与运营工作区。</p></div></header>
      <ManagerContent csrfToken={csrfToken} elfieCount={elfieCount} onElfieCountChange={setElfieCount} tab={tab} />
    </section>
  </section></main>
}

function ManagerContent({ csrfToken, elfieCount, onElfieCountChange, tab }: { readonly csrfToken: string; readonly elfieCount: number; readonly onElfieCountChange: (count: number) => void; readonly tab: ManagerTab }) {
  switch (tab) {
    case "monitor": return <MonitorPanel csrfToken={csrfToken} elfieCount={elfieCount} />
    case "elfies": return <OwnerElfieOverview onCountChange={onElfieCountChange} />
    case "nest": return <OwnerNestPanel csrfToken={csrfToken} />
    case "users": return <UsersPanel csrfToken={csrfToken} />
    case "providers": return <OwnerProviderPanel csrfToken={csrfToken} />
    case "models": return <OwnerModelPanel csrfToken={csrfToken} />
    case "tools": return <OwnerToolPanel csrfToken={csrfToken} />
    case "foods": return <OwnerFoodPanel csrfToken={csrfToken} />
    case "logs": return <OwnerDataPanel csrfToken={csrfToken} description="最近运行审计事件，来源于实际运行时。" readPath="/api/owner/runtime/audit" title="运行日志" />
    case "system": return <SystemPanels csrfToken={csrfToken} />
    case "godot": return <GodotPanels csrfToken={csrfToken} />
  }
}

function MonitorPanel({ csrfToken, elfieCount }: { readonly csrfToken: string; readonly elfieCount: number }) {
  return <section className="manage-grid"><Card description="真实服务、模型、数据库与 Godot 的运行摘要。" title="综合监控"><p className="metric">{elfieCount} <small>位已筛选精灵</small></p><a className="button button--quiet" href="/manage?section=elfies">查看全部精灵</a></Card><section className="manage-card manage-card--wide"><OwnerDataPanel csrfToken={csrfToken} description="实际健康、运行配置与模型服务状态。" readPath="/api/owner/runtime/status" title="服务状态" /></section></section>
}

function UsersPanel({ csrfToken }: { readonly csrfToken: string }) {
  const [users, setUsers] = useState<readonly OwnerUser[]>([])
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const load = async (): Promise<void> => { try { setUsers(await ownerUsers()); setError(null) } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "用户列表加载失败") } }
  useEffect(() => { void load() }, [])
  const create = async (event: FormEvent<HTMLFormElement>): Promise<void> => { event.preventDefault(); try { const created = await createManagedUser(username.trim(), password, csrfToken); setUsers((current) => [...current, { ...created, elfie_count: 0 }]); setUsername(""); setPassword(""); setNotice("普通用户已创建，登录后将进入聊天页。"); setError(null) } catch (reason: unknown) { setError(reason instanceof ApiError ? reason.message : "用户未创建") } }
  return <section className="manage-card manage-card--wide"><div className="manage-head"><div><h2>用户管理</h2><p>仅管理账户；精灵只能由用户在聊天页自行领养。</p></div><button className="button button--quiet" onClick={() => { void load() }} type="button">刷新</button></div>{error && <Notice kind="error" message={error} />}{notice && <Notice message={notice} />}<ul className="manage-list">{users.map((entry) => <li key={entry.id}>{entry.username} · {entry.elfie_count} 位精灵</li>)}</ul><form className="manage-form" onSubmit={(event) => { void create(event) }}><input onChange={(event) => setUsername(event.target.value)} placeholder="新用户名" required value={username} /><input autoComplete="new-password" onChange={(event) => setPassword(event.target.value)} placeholder="初始密码" required type="password" value={password} /><button className="button" type="submit">创建普通用户</button></form></section>
}

function SystemPanels({ csrfToken }: { readonly csrfToken: string }) {
  return <section className="manage-grid manager-modules"><OwnerDataPanel csrfToken={csrfToken} description="系统运行约束；保存前由后端校验。" readPath="/api/owner/system/engine" title="引擎设置" writePath="/api/owner/system/engine" /><OwnerDataPanel csrfToken={csrfToken} description="领养物种、人格与容量。" readPath="/api/owner/system/adoption" title="领养设置" writePath="/api/owner/system/adoption" /><OwnerDataPanel csrfToken={csrfToken} description="会话与安全限制。" readPath="/api/owner/system/security" title="安全设置" writePath="/api/owner/system/security" /><OwnerDataPanel csrfToken={csrfToken} description="运行时任务到粮食的策略。" readPath="/api/owner/runtime/policy" title="运行策略" writePath="/api/owner/runtime/policy" /></section>
}

function GodotPanels({ csrfToken }: { readonly csrfToken: string }) {
  return <section className="manage-grid manager-modules"><OwnerDataPanel csrfToken={csrfToken} description="Godot Web Runtime 构建和资源状态。" readPath="/api/godot-web/status" title="Godot Web Runtime" /><CameraPreview csrfToken={csrfToken} /><section className="manage-card"><h2>房间预览</h2><p>打开独立 Godot Runtime，预览固定精灵巢场景。</p><a className="button" href="/runtime/godot">打开 3D 预览</a></section></section>
}
