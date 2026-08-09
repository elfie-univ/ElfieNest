import { useState } from "react"
import { useTranslation } from "react-i18next"

import { OwnerElfieOverview } from "../components/OwnerElfieOverview"
import { OwnerFoodPanel } from "../components/OwnerFoodPanel"
import { OwnerNestPanel } from "../components/OwnerNestPanel"
import { OwnerProviderPanel } from "../components/OwnerProviderPanel"
import { ManageMonitorPanel } from "../components/ManageMonitorPanel"
import { ManageUsersPanel } from "../components/ManageUsersPanel"
import { ManageSidebar } from "../components/ManageSidebar"
import { SystemSettingsPanel } from "../components/SystemSettingsPanel"
import { useSession } from "../stores/session"
import { usePresenceHeartbeat } from "../stores/heartbeat"
import { isManagerRole, type AccountRole } from "../api/roles"
import { isManageTab, manageNavItem, type ManageTab } from "./manageNavigation"

function initialTab(): ManageTab {
  const requested = new URLSearchParams(window.location.search).get("section")
  return isManageTab(requested) ? requested : "monitor"
}

export function ManagePage() {
  const { t } = useTranslation("manage")
  const { user, loading, refresh } = useSession()
  usePresenceHeartbeat(user)
  const [tab, setTab] = useState<ManageTab>(initialTab)
  if (loading) return <main className="page"><p className="empty">{t("page.verifyingSession")}</p></main>
  if (user === null || !isManagerRole(user.role)) { window.location.assign(user === null ? "/login?next=/manage" : "/chat"); return <main /> }
  const csrfToken = user.csrf_token ?? ""
  const chooseTab = (next: ManageTab): void => {
    setTab(next)
    window.history.replaceState({}, "", `/manage?section=${next}`)
  }
  const currentItem = manageNavItem(tab)
  return <main className="app-page"><section className="manage-workbench manage-workbench--console">
    <ManageSidebar activeTab={tab} onSelect={chooseTab} onUserUpdated={refresh} user={user} />
    <section className="panel manage manage--console">
      <header className="manage-console-head"><h1>{currentItem ? t(`navigation.items.${currentItem.id}`) : t("page.title")}</h1></header>
      <ManageContent actorRole={user.role} csrfToken={csrfToken} onElfieCountChange={() => undefined} tab={tab} />
    </section>
  </section></main>
}

function ManageContent({ actorRole, csrfToken, onElfieCountChange, tab }: { readonly actorRole: AccountRole; readonly csrfToken: string; readonly onElfieCountChange: (count: number) => void; readonly tab: ManageTab }) {
  switch (tab) {
    case "monitor": return <ManageMonitorPanel />
    case "elfies": return <OwnerElfieOverview csrfToken={csrfToken} onCountChange={onElfieCountChange} />
    case "nest": return <OwnerNestPanel csrfToken={csrfToken} />
    case "users": return <ManageUsersPanel actorRole={actorRole} csrfToken={csrfToken} />
    case "providers": return <OwnerProviderPanel csrfToken={csrfToken} />
    case "foods": return <OwnerFoodPanel csrfToken={csrfToken} />
    case "system": return <SystemSettingsPanel csrfToken={csrfToken} />
  }
}
