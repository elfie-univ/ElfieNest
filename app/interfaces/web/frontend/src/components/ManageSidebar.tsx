import { useState } from "react"
import { useTranslation } from "react-i18next"

import type { ClientUser } from "../api/client"
import type { ManageTab } from "../pages/manageNavigation"
import { MANAGE_NAV_GROUPS } from "../pages/manageNavigation"
import { AccountMenu } from "./AccountMenu"
import { Icon } from "./Icon"
import { MobileAccessDialog } from "./MobileAccessDialog"

const manageFullLogoUrl = new URL("../../../../../../docs/public/assets/elfienest-full-logo-transparent.png", import.meta.url).href

type ManageSidebarProps = {
  readonly activeTab: ManageTab
  readonly onSelect: (tab: ManageTab) => void
  readonly onUserUpdated: () => Promise<void>
  readonly user: ClientUser
}

export function ManageSidebar({ activeTab, onSelect, onUserUpdated, user }: ManageSidebarProps) {
  const { t } = useTranslation("manage")
  const [showMobileAccess, setShowMobileAccess] = useState(false)
  return <aside aria-label={t("sidebar.label")} className="manage-sidebar">
    <div className="manage-sidebar__brand"><img alt="ELFIE NEST" className="manage-sidebar__brand-logo" src={manageFullLogoUrl} /></div>
    <nav className="manage-sidebar__navigation">
      {MANAGE_NAV_GROUPS.map((group) => <section aria-label={t(`navigation.groups.${group.id}`)} className="manage-nav-group" key={group.id} role="group"><p aria-hidden="true">{t(`navigation.groups.${group.id}`)}</p>{group.items.map((item) => <button aria-current={activeTab === item.id ? "page" : undefined} className={activeTab === item.id ? "manage-nav-item manage-nav-item--active" : "manage-nav-item"} data-slot="button" data-variant="ghost" key={item.id} onClick={() => onSelect(item.id)} type="button"><Icon name={item.icon} size={17} />{t(`navigation.items.${item.id}`)}</button>)}</section>)}
    </nav>
    <div className="manage-sidebar__bottom">
      <div aria-label={t("sidebar.quickActions")} className="manage-sidebar__quick-actions"><a aria-label={t("sidebar.openMonitor")} className="manage-quick-action" data-slot="button" data-tooltip={t("sidebar.openMonitor")} data-variant="ghost" href="/monitor"><Icon name="cctv" /></a><a aria-label={t("sidebar.openChat")} className="manage-quick-action" data-slot="button" data-tooltip={t("sidebar.openChat")} data-variant="ghost" href="/chat"><Icon name="messages-square" /></a><button aria-label={t("sidebar.openMobile")} className="manage-quick-action manage-quick-action--mobile-access" data-slot="button" data-tooltip={t("sidebar.openMobileTooltip")} data-variant="ghost" onClick={() => setShowMobileAccess(true)} type="button"><Icon name="qr-code" /></button></div>
      <AccountMenu onUpdated={onUserUpdated} user={user} />
    </div>
    {showMobileAccess ? <MobileAccessDialog onClose={() => setShowMobileAccess(false)} targetPath="/manage" /> : null}
  </aside>
}
