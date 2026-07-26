import { useState } from "react"

import { OwnerElfieOverview } from "../components/OwnerElfieOverview"
import { OwnerFoodPanel } from "../components/OwnerFoodPanel"
import { OwnerNestPanel } from "../components/OwnerNestPanel"
import { OwnerProviderPanel } from "../components/OwnerProviderPanel"
import { ManageMonitorPanel } from "../components/ManageMonitorPanel"
import { ManageUsersPanel } from "../components/ManageUsersPanel"
import { ManageSidebar } from "../components/ManageSidebar"
import { SystemSettingsPanel } from "../components/SystemSettingsPanel"
import { useSession } from "../stores/session"
import { IconCatalogPage } from "./IconCatalogPage"
import { isManageTab, manageNavItem, type ManageTab } from "./manageNavigation"

function initialTab(): ManageTab {
  const requested = new URLSearchParams(window.location.search).get("section")
  return isManageTab(requested) ? requested : "monitor"
}

export function ManagePage() {
  const { user, loading, refresh } = useSession()
  const [tab, setTab] = useState<ManageTab>(initialTab)
  const [elfieCount, setElfieCount] = useState(0)
  if (loading) return <main className="page"><p className="empty">正在验证会话…</p></main>
  if (user?.role !== "owner") { window.location.assign(user === null ? "/login?next=/manage" : "/chat"); return <main /> }
  if (new URLSearchParams(window.location.search).get("icon-catalog") === "1") return <IconCatalogPage />
  const csrfToken = user.csrf_token ?? ""
  const chooseTab = (next: ManageTab): void => {
    setTab(next)
    window.history.replaceState({}, "", `/manage?section=${next}`)
  }
  const currentItem = manageNavItem(tab)
  return <main className="app-page"><section className="manage-workbench manage-workbench--console">
    <ManageSidebar activeTab={tab} onSelect={chooseTab} onUserUpdated={refresh} user={user} />
    <section className="panel manage manage--console">
      <header className="manage-console-head"><h1>{currentItem?.label ?? "管理台"}</h1></header>
      <ManageContent csrfToken={csrfToken} elfieCount={elfieCount} onElfieCountChange={setElfieCount} tab={tab} />
    </section>
  </section></main>
}

function ManageContent({ csrfToken, elfieCount, onElfieCountChange, tab }: { readonly csrfToken: string; readonly elfieCount: number; readonly onElfieCountChange: (count: number) => void; readonly tab: ManageTab }) {
  switch (tab) {
    case "monitor": return <ManageMonitorPanel elfieCount={elfieCount} />
    case "elfies": return <OwnerElfieOverview csrfToken={csrfToken} onCountChange={onElfieCountChange} />
    case "nest": return <OwnerNestPanel csrfToken={csrfToken} />
    case "users": return <ManageUsersPanel csrfToken={csrfToken} />
    case "providers": return <OwnerProviderPanel csrfToken={csrfToken} />
    case "tools": return <ToolPlaceholder />
    case "foods": return <OwnerFoodPanel csrfToken={csrfToken} />
    case "system": return <SystemSettingsPanel csrfToken={csrfToken} />
  }
}

function ToolPlaceholder() {
  return <section className="manage-card manage-card--wide manage-empty-state"><p>这部分需要先定义"谁可调用什么工具、权限如何继承和审计"的产品规则；在规则确定前，不展示不可读的原始配置。</p><span>即将设计</span></section>
}
