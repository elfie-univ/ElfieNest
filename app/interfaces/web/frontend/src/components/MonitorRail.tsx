import { Button } from "@/components/ui/button"
import { useTranslation } from "react-i18next"

import type { ClientUser } from "../api/client"
import { AppRail } from "./AppRail"
import { Icon } from "./Icon"

type MonitorRailProps = {
  readonly onMobileAccess: () => void
  readonly onToggleImmersive: () => void
  readonly onUpdated: () => Promise<void>
  readonly user: ClientUser
}

export function MonitorRail({ onMobileAccess, onToggleImmersive, onUpdated, user }: MonitorRailProps) {
  const { t: tChat } = useTranslation("chat")
  const { t: tManage } = useTranslation("manage")
  const { t: tMonitor } = useTranslation("monitor")
  return <AppRail
    ariaLabel={tMonitor("navigation.railLabel")}
    links={[
      { href: "/manage", icon: "house", label: tChat("navigation.manage") },
      { href: "/chat", icon: "messages-square", label: tManage("sidebar.openChat") },
    ]}
    mobileAccessLabel={tMonitor("navigation.mobileAccess")}
    onMobileAccess={onMobileAccess}
    onUpdated={onUpdated}
    user={user}
  >
    <nav aria-label={tMonitor("navigation.controls")} className="rail-nav">
      <Button aria-label={tMonitor("navigation.immersive")} className="rail-button" data-tooltip={tMonitor("navigation.immersive")} onClick={onToggleImmersive} size="icon" type="button" variant="ghost"><Icon name="maximize-2" /></Button>
    </nav>
  </AppRail>
}
