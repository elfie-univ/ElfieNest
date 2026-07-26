import { useState } from "react"

import type { ClientUser } from "../api/client"
import type { ManagerTab } from "../pages/managerNavigation"
import { MANAGER_NAV_GROUPS } from "../pages/managerNavigation"
import { AccountMenu } from "./AccountMenu"
import { Avatar } from "./Avatar"
import { Icon } from "./Icon"
import { MobileAccessDialog } from "./MobileAccessDialog"

type ManagerSidebarProps = {
  readonly activeTab: ManagerTab
  readonly onSelect: (tab: ManagerTab) => void
  readonly onUserUpdated: () => Promise<void>
  readonly user: ClientUser
}

export function ManagerSidebar({ activeTab, onSelect, onUserUpdated, user }: ManagerSidebarProps) {
  const [showMobileAccess, setShowMobileAccess] = useState(false)
  return <aside aria-label="ElfieNest 管理导航" className="manager-sidebar">
    <div className="manager-sidebar__brand"><Avatar name="管" /><span><strong>ELFIE NEST</strong><small>OWNER CONSOLE</small></span></div>
    <nav className="manager-sidebar__navigation">
      {MANAGER_NAV_GROUPS.map((group) => <section className="manager-nav-group" key={group.label}><p>{group.label}</p>{group.items.map((item) => <button aria-current={activeTab === item.id ? "page" : undefined} className={activeTab === item.id ? "manager-nav-item manager-nav-item--active" : "manager-nav-item"} key={item.id} onClick={() => onSelect(item.id)} type="button"><Icon name={item.icon} size={17} />{item.label}</button>)}</section>)}
    </nav>
    <div className="manager-sidebar__bottom">
      <div aria-label="快捷入口" className="manager-sidebar__quick-actions"><a aria-label="进入聊天" className="manager-quick-action" data-tooltip="进入聊天" href="/chat"><Icon name="messages-square" /></a><button aria-label="用手机打开管理台" className="manager-quick-action" data-tooltip="扫码用手机打开管理台" onClick={() => setShowMobileAccess(true)} type="button"><Icon name="qr-code" /></button></div>
      <AccountMenu onUpdated={onUserUpdated} user={user} />
    </div>
    {showMobileAccess ? <MobileAccessDialog onClose={() => setShowMobileAccess(false)} targetPath="/manage" /> : null}
  </aside>
}
