import { useState } from "react"

import type { ClientUser } from "../api/client"
import type { ManageTab } from "../pages/manageNavigation"
import { MANAGE_NAV_GROUPS } from "../pages/manageNavigation"
import { AccountMenu } from "./AccountMenu"
import { Avatar } from "./Avatar"
import { Icon } from "./Icon"
import { MobileAccessDialog } from "./MobileAccessDialog"

const manageLogoUrl = new URL("../../../../../../docs/public/assets/logo.png", import.meta.url).href

type ManageSidebarProps = {
  readonly activeTab: ManageTab
  readonly onSelect: (tab: ManageTab) => void
  readonly onUserUpdated: () => Promise<void>
  readonly user: ClientUser
}

export function ManageSidebar({ activeTab, onSelect, onUserUpdated, user }: ManageSidebarProps) {
  const [showMobileAccess, setShowMobileAccess] = useState(false)
  return <aside aria-label="ElfieNest 管理导航" className="manage-sidebar">
    <div className="manage-sidebar__brand"><span className="manage-sidebar__logo"><span aria-hidden="true">管</span><img alt="ElfieNest" onError={(event) => { event.currentTarget.hidden = true }} src={manageLogoUrl} /></span><span className="manage-sidebar__brand-text"><strong>ELFIE NEST</strong></span></div>
    <nav className="manage-sidebar__navigation">
      {MANAGE_NAV_GROUPS.map((group) => <section aria-label={group.label} className="manage-nav-group" key={group.label} role="group"><p aria-hidden="true">{group.label}</p>{group.items.map((item) => <button aria-current={activeTab === item.id ? "page" : undefined} className={activeTab === item.id ? "manage-nav-item manage-nav-item--active" : "manage-nav-item"} data-slot="button" data-variant="ghost" key={item.id} onClick={() => onSelect(item.id)} type="button"><Icon name={item.icon} size={17} />{item.label}</button>)}</section>)}
    </nav>
    <div className="manage-sidebar__bottom">
      <div aria-label="快捷入口" className="manage-sidebar__quick-actions"><a aria-label="进入聊天" className="manage-quick-action" data-slot="button" data-tooltip="进入聊天" data-variant="ghost" href="/chat"><Icon name="messages-square" /></a><button aria-label="用手机打开管理台" className="manage-quick-action" data-slot="button" data-tooltip="扫码用手机打开管理台" data-variant="ghost" onClick={() => setShowMobileAccess(true)} type="button"><Icon name="qr-code" /></button></div>
      <AccountMenu onUpdated={onUserUpdated} user={user} />
    </div>
    {showMobileAccess ? <MobileAccessDialog onClose={() => setShowMobileAccess(false)} targetPath="/manage" /> : null}
  </aside>
}
