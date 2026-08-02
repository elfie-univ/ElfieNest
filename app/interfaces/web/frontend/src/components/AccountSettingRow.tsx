import type { ReactNode } from "react"

import { Icon, type IconName } from "./Icon"

type AccountSettingRowProps = {
  readonly active: boolean
  readonly children: ReactNode
  readonly icon: IconName
  readonly label: string
  readonly onToggle: () => void
  readonly summary: string
}

export function AccountSettingRow({ active, children, icon, label, onToggle, summary }: AccountSettingRowProps) {
  return <section className={active ? "account-menu__setting account-menu__setting--active" : "account-menu__setting"}>
    <button aria-expanded={active} className="account-menu__setting-toggle" data-slot="button" data-variant="ghost" onClick={onToggle} type="button">
      <Icon name={icon} size={17} />
      <span><strong>{label}</strong><small>{summary}</small></span>
      <Icon name={active ? "chevron-up" : "chevron-down"} size={17} />
    </button>
    {active ? <div className="account-menu__setting-body">{children}</div> : null}
  </section>
}
