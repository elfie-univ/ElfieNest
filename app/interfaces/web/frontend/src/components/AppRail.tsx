import { Button } from "@/components/ui/button"
import type { ReactNode } from "react"

import type { ClientUser } from "../api/client"
import type { IconName } from "./Icon"
import { AccountMenu } from "./AccountMenu"
import { Icon } from "./Icon"

export type AppRailLink = {
  readonly href: string
  readonly icon: IconName
  readonly label: string
}

type AppRailProps = {
  readonly ariaLabel: string
  readonly children: ReactNode
  readonly links: readonly AppRailLink[]
  readonly mobileAccessLabel: string
  readonly onMobileAccess: () => void
  readonly onUpdated: () => Promise<void>
  readonly user: ClientUser
}

export function AppRail({
  ariaLabel,
  children,
  links,
  mobileAccessLabel,
  onMobileAccess,
  onUpdated,
  user,
}: AppRailProps) {
  return <aside aria-label={ariaLabel} className="app-rail">
    {children}
    <div className="rail-bottom">
      <div className="rail-quick-actions">
        {links.map((link) => <Button asChild className={link.icon === "house" ? "rail-button rail-button--manage" : "rail-button"} data-tooltip={link.label} key={link.href} size="icon" variant="ghost"><a aria-label={link.label} href={link.href}><Icon name={link.icon} /></a></Button>)}
        <Button aria-label={mobileAccessLabel} className="rail-button rail-button--mobile-access" data-tooltip={mobileAccessLabel} onClick={onMobileAccess} size="icon" type="button" variant="ghost"><Icon name="qr-code" /></Button>
      </div>
      <AccountMenu compact onUpdated={onUpdated} user={user} />
    </div>
  </aside>
}
