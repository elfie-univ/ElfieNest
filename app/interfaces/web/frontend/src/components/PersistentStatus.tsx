import { Button } from "@/components/ui/button"

import type { NotificationKind, ToastAction } from "./notification-types"
import { Notice } from "./Notice"

type PersistentStatusKind = Exclude<NotificationKind, "success">

type PersistentStatusProps = {
  readonly detail?: string
  readonly details?: ToastAction
  readonly kind: PersistentStatusKind
  readonly message: string
  readonly retry?: ToastAction
}

export function PersistentStatus({ detail, details, kind, message, retry }: PersistentStatusProps) {
  return <div className="persistent-status" data-kind={kind}>
    <Notice kind={kind} message={message} />
    {detail ? <p className="persistent-status__detail">{detail}</p> : null}
    {retry || details ? <div className="persistent-status__actions">
      {retry ? <Button onClick={retry.onSelect} size="sm" type="button">{retry.label}</Button> : null}
      {details ? <Button onClick={details.onSelect} size="sm" type="button" variant="outline">{details.label}</Button> : null}
    </div> : null}
  </div>
}
