import type { ReactNode } from "react"
import { Icon } from "./Icon"

export function InlineBanner({ children, role, tone }: {
  readonly children: ReactNode
  readonly role: "alert" | "status"
  readonly tone: "error" | "notice"
}) {
  return (
    <div className={`inline-banner inline-banner--${tone}`} role={role}>
      <Icon aria-hidden="true" name="triangle-alert" size={16} />
      <span>{children}</span>
    </div>
  )
}
