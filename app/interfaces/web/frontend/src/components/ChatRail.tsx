import { Button } from "@/components/ui/button"
import { useTranslation } from "react-i18next"

import type { ClientUser } from "../api/client"
import { isManagerRole } from "../api/roles"
import type { ChatPane } from "../pages/use-chat-view"
import { AccountMenu } from "./AccountMenu"
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
  return (
    <aside className="app-rail" aria-label={t("navigation.railLabel")}>
      <nav className="rail-nav">
        <Button aria-label={t("navigation.chats")} className={activePane === "chats" ? "rail-button rail-button--active" : "rail-button"} data-tooltip={t("navigation.chats")} onClick={() => onOpenSection("chats")} size="icon" type="button" variant="ghost"><Icon name="messages-square" /></Button>
        <Button aria-label={t("navigation.elfies")} className={activePane === "elfies" ? "rail-button rail-button--active" : "rail-button"} data-tooltip={t("navigation.elfies")} onClick={() => onOpenSection("elfies")} size="icon" type="button" variant="ghost"><Icon name="users" /></Button>
      </nav>
      <div className="rail-bottom">
        <div className="rail-quick-actions">
          {isManagerRole(user.role) ? (
            <>
              <Button asChild className="rail-button rail-button--manage" data-tooltip={t("navigation.manage")} size="icon" variant="ghost"><a aria-label={t("navigation.manage")} href="/manage"><Icon name="house" /></a></Button>
              <Button asChild className="rail-button" data-tooltip={t("navigation.monitor")} size="icon" variant="ghost"><a aria-label={t("navigation.monitor")} href="/monitor"><Icon name="cctv" /></a></Button>
            </>
          ) : null}
          <Button aria-label={t("navigation.mobileAccess")} className="rail-button rail-button--mobile-access" data-tooltip={t("navigation.mobileAccess")} onClick={onMobileAccess} size="icon" type="button" variant="ghost"><Icon name="qr-code" /></Button>
        </div>
        <AccountMenu compact onUpdated={onUpdated} user={user} />
      </div>
    </aside>
  )
}
