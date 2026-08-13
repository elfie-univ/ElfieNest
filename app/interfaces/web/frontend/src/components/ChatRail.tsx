import { Button } from "@/components/ui/button"
import { useTranslation } from "react-i18next"

import type { ClientUser } from "../api/client"
import { isManagerRole } from "../api/roles"
import type { ChatPane } from "../pages/use-chat-view"
import { AppRail, type AppRailLink } from "./AppRail"
import { Icon } from "./Icon"

type ChatRailProps = {
  readonly activePane: ChatPane
  readonly onMobileAccess: () => void
  readonly onOpenSection: (section: ChatPane) => void
  readonly onUpdated: () => Promise<void>
  readonly user: ClientUser
}

export function ChatRail({ activePane, onMobileAccess, onOpenSection, onUpdated, user }: ChatRailProps) {
  const { t } = useTranslation("chat")
  const links: readonly AppRailLink[] = isManagerRole(user.role)
    ? [
      { href: "/manage", icon: "house", label: t("navigation.manage") },
      { href: "/monitor", icon: "cctv", label: t("navigation.monitor") },
    ]
    : []
  return <AppRail ariaLabel={t("navigation.railLabel")} links={links} mobileAccessLabel={t("navigation.mobileAccess")} onMobileAccess={onMobileAccess} onUpdated={onUpdated} user={user}>
      <nav className="rail-nav">
        <Button aria-label={t("navigation.chats")} className={activePane === "chats" ? "rail-button rail-button--active" : "rail-button"} data-tooltip={t("navigation.chats")} onClick={() => onOpenSection("chats")} size="icon" type="button" variant="ghost"><Icon name="messages-square" /></Button>
        <Button aria-label={t("navigation.elfies")} className={activePane === "elfies" ? "rail-button rail-button--active" : "rail-button"} data-tooltip={t("navigation.elfies")} onClick={() => onOpenSection("elfies")} size="icon" type="button" variant="ghost"><Icon name="users" /></Button>
      </nav>
  </AppRail>
}
